from __future__ import annotations

import operator
import pickle
import random

import pytest

from distributed.collections import LRU, HeapSet


def test_lru():
    l = LRU(maxsize=3)
    l["a"] = 1
    l["b"] = 2
    l["c"] = 3
    assert list(l.keys()) == ["a", "b", "c"]

    # Use "a" and ensure it becomes the most recently used item
    l["a"]
    assert list(l.keys()) == ["b", "c", "a"]

    # Ensure maxsize is respected
    l["d"] = 4
    assert len(l) == 3
    assert list(l.keys()) == ["c", "a", "d"]


class C:
    def __init__(self, k, i):
        self.k = k
        self.i = i

    def __hash__(self):
        return hash(self.k)

    def __eq__(self, other):
        return isinstance(other, C) and other.k == self.k


def test_heapset():
    heap = HeapSet(key=operator.attrgetter("i"))

    cx = C("x", 2)
    cy = C("y", 1)
    cz = C("z", 3)
    cw = C("w", 4)
    heap.add(cx)
    heap.add(cy)
    heap.add(cz)
    heap.add(cw)
    heap.add(C("x", 0))  # Ignored; x already in heap
    assert len(heap) == 4
    assert repr(heap) == "<HeapSet: 4 items>"

    assert cx in heap
    assert cy in heap
    assert cz in heap
    assert cw in heap

    heap_sorted = heap.sorted()
    # iteration does not empty heap
    assert len(heap) == 4
    assert next(heap_sorted) is cy
    assert next(heap_sorted) is cx
    assert next(heap_sorted) is cz
    assert next(heap_sorted) is cw
    with pytest.raises(StopIteration):
        next(heap_sorted)

    assert set(heap) == {cx, cy, cz, cw}

    assert heap.peek() is cy
    assert heap.pop() is cy
    assert cx in heap
    assert cy not in heap
    assert cz in heap
    assert cw in heap

    assert heap.peek() is cx
    assert heap.pop() is cx
    assert heap.pop() is cz
    assert heap.pop() is cw
    assert not heap
    with pytest.raises(KeyError):
        heap.pop()
    with pytest.raises(KeyError):
        heap.peek()

    # Test out-of-order discard
    heap.add(cx)
    heap.add(cy)
    heap.add(cz)
    heap.add(cw)
    assert heap.peek() is cy

    heap.remove(cy)
    assert cy not in heap
    with pytest.raises(KeyError):
        heap.remove(cy)

    heap.discard(cw)
    assert cw not in heap
    heap.discard(cw)

    assert len(heap) == 2
    assert list(heap.sorted()) == [cx, cz]
    # cy is at the top of heap._heap, but is skipped
    assert heap.peek() is cx
    assert heap.pop() is cx
    assert heap.peek() is cz
    assert heap.pop() is cz
    # heap._heap is not empty
    assert not heap
    with pytest.raises(KeyError):
        heap.peek()
    with pytest.raises(KeyError):
        heap.pop()
    assert list(heap.sorted()) == []

    # Test clear()
    heap.add(cx)
    heap.clear()
    assert not heap
    heap.add(cx)
    assert cx in heap
    # Test discard last element
    heap.discard(cx)
    assert not heap
    heap.add(cx)
    assert cx in heap

    # Test resilience to failure in key()
    bad_key = C("bad_key", 0)
    del bad_key.i
    with pytest.raises(AttributeError):
        heap.add(bad_key)
    assert len(heap) == 1
    assert set(heap) == {cx}

    # Test resilience to failure in weakref.ref()
    class D:
        __slots__ = ("i",)

        def __init__(self, i):
            self.i = i

    with pytest.raises(TypeError):
        heap.add(D("bad_weakref", 2))
    assert len(heap) == 1
    assert set(heap) == {cx}

    # Test resilience to key() returning non-sortable output
    with pytest.raises(TypeError):
        heap.add(C("unsortable_key", None))
    assert len(heap) == 1
    assert set(heap) == {cx}


def test_heapset_pickle():
    """Test pickle roundtrip for a HeapSet.

    Note
    ----
    To make this test work with plain pickle and not need cloudpickle, we had to avoid
    lambdas and local classes in our test. Here we're testing that HeapSet doesn't add
    lambdas etc. of its own.
    """
    heap = HeapSet(key=operator.attrgetter("i"))

    # The heap contains broken weakrefs
    for i in range(200):
        c = C(f"y{i}", random.random())
        heap.add(c)
        if random.random() > 0.7:
            heap.remove(c)

    heap2 = pickle.loads(pickle.dumps(heap))
    assert len(heap) == len(heap2)
    # Test that the heap has been re-heapified upon unpickle
    assert len(heap2._heap) < len(heap._heap)
    while heap:
        assert heap.pop() == heap2.pop()
