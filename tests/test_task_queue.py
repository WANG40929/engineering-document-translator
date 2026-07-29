from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from translator_app.task_queue import PreemptiveTaskQueue


class PreemptiveTaskQueueTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="udt_queue_")
        root = Path(self.temporary.name)
        self.paths = [root / f"{name}.pdf" for name in ("a", "b", "c", "urgent")]

    def tearDown(self):
        self.temporary.cleanup()

    def test_waiting_file_moves_ahead_of_normal_queue(self):
        queue = PreemptiveTaskQueue(self.paths[:3])
        self.assertEqual(queue.pop_next(), str(self.paths[0].resolve()))
        accepted, added = queue.prioritize(self.paths[2])
        self.assertTrue(accepted)
        self.assertFalse(added)
        queue.requeue_current(self.paths[0])
        self.assertEqual(queue.pop_next(), str(self.paths[2].resolve()))
        queue.complete_current(self.paths[2])
        self.assertEqual(queue.pop_next(), str(self.paths[0].resolve()))
        queue.complete_current(self.paths[0])
        self.assertEqual(queue.pop_next(), str(self.paths[1].resolve()))

    def test_new_urgent_file_joins_active_run(self):
        queue = PreemptiveTaskQueue(self.paths[:2])
        queue.pop_next()
        accepted, added = queue.prioritize(self.paths[3])
        self.assertTrue(accepted)
        self.assertTrue(added)
        self.assertEqual(queue.total_count, 3)
        queue.requeue_current(self.paths[0])
        self.assertEqual(queue.pending_snapshot()[0], str(self.paths[3].resolve()))

    def test_latest_urgent_file_preempts_earlier_urgent_file(self):
        queue = PreemptiveTaskQueue(self.paths[:3])
        queue.pop_next()
        queue.prioritize(self.paths[1])
        queue.prioritize(self.paths[2])
        queue.requeue_current(self.paths[0])
        self.assertEqual(
            queue.pending_snapshot(),
            [
                str(self.paths[2].resolve()),
                str(self.paths[1].resolve()),
                str(self.paths[0].resolve()),
            ],
        )

    def test_waiting_file_can_be_removed_without_stopping_current(self):
        queue = PreemptiveTaskQueue(self.paths[:3])
        queue.pop_next()
        self.assertTrue(queue.remove(self.paths[1]))
        self.assertFalse(queue.remove(self.paths[0]))
        self.assertNotIn(str(self.paths[1].resolve()), queue.snapshot())

    def test_queue_rejects_new_work_after_worker_observes_empty(self):
        queue = PreemptiveTaskQueue([self.paths[0]])
        queue.pop_next()
        queue.complete_current(self.paths[0])
        self.assertIsNone(queue.pop_next())
        self.assertEqual(queue.prioritize(self.paths[3]), (False, False))


if __name__ == "__main__":
    unittest.main()
