
from atlas.core import Scheduler
from atlas.task import FuncTask
from atlas.time import TimeDelta
from atlas.core.task.base import Task
from atlas.core.exceptions import TaskTerminationException
from atlas.conditions import SchedulerCycles, SchedulerStarted, TaskFinished, TaskStarted, AlwaysFalse, AlwaysTrue
from atlas import session

import pytest
import pandas as pd

import logging
import sys
import time
import os
import multiprocessing

def run_slow():
    time.sleep(0.2)
    with open("work.txt", "a") as file:
        file.write("line created\n")

def run_slow_threaded(_thread_terminate_):
    time.sleep(0.2)
    if _thread_terminate_.is_set():
        raise TaskTerminationException
    else:
        with open("work.txt", "a") as file:
            file.write("line created\n")


@pytest.mark.parametrize("execution", ["thread", "process"])
def test_without_timeout(tmpdir, execution):
    with tmpdir.as_cwd() as old_dir:
        session.reset()
        func_run_slow = run_slow if execution == "process" else run_slow_threaded
        task = FuncTask(func_run_slow, name="slow task but passing", start_cond=AlwaysTrue(), timeout="never", execution=execution)

        scheduler = Scheduler(
            shut_condition=TaskFinished(task="slow task but passing") >= 2,
            timeout="0.1 seconds"
        )
        scheduler()

        history = pd.DataFrame(task.get_history())
        # If Scheduler is quick, it may launch the task 3 times 
        # but there still should not be any terminations
        assert 2 <= (history["action"] == "run").sum()
        assert 0 == (history["action"] == "terminate").sum()
        assert 2 <= (history["action"] == "success").sum()
        assert 0 == (history["action"] == "fail").sum()

        assert os.path.exists("work.txt")

@pytest.mark.parametrize("execution", ["thread", "process"])
def test_task_timeout(tmpdir, execution):
    with tmpdir.as_cwd() as old_dir:
        session.reset()
        func_run_slow = run_slow if execution == "process" else run_slow_threaded
        task = FuncTask(func_run_slow, name="slow task", start_cond=AlwaysTrue(), execution=execution)

        scheduler = Scheduler(
            shut_condition=TaskStarted(task="slow task") >= 2,
            timeout="0.1 seconds"
        )
        scheduler()

        history = pd.DataFrame(task.get_history())
        assert 2 == (history["action"] == "run").sum()
        assert 2 == (history["action"] == "terminate").sum()
        assert 0 == (history["action"] == "success").sum()
        assert 0 == (history["action"] == "fail").sum()

        assert not os.path.exists("work.txt")

@pytest.mark.parametrize("execution", ["thread", "process"])
def test_task_terminate(tmpdir, execution):

    def terminate_task(_scheduler_):
        _scheduler_.tasks[0].force_termination = True

    with tmpdir.as_cwd() as old_dir:
        session.reset()
        func_run_slow = run_slow if execution == "process" else run_slow_threaded
        task = FuncTask(func_run_slow, name="slow task", start_cond=AlwaysTrue(), execution=execution)

        FuncTask(terminate_task, name="terminator", start_cond=TaskStarted(task="slow task"), execution="main")
        scheduler = Scheduler(
            shut_condition=TaskStarted(task="slow task") >= 2,
        )
        scheduler()

        history = pd.DataFrame(task.get_history())
        assert 2 == (history["action"] == "run").sum()
        assert 2 == (history["action"] == "terminate").sum()
        assert 0 == (history["action"] == "success").sum()
        assert 0 == (history["action"] == "fail").sum()

        assert not os.path.exists("work.txt")

        # Attr force_termination should be reseted every time the task has been terminated
        assert not task.force_termination

