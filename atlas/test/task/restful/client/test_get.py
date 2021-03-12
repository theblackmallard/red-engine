
import tempfile

import pytest

from atlas.task.api import HTTPConnection
from atlas.task import FuncTask
from atlas import Scheduler, session
from atlas.conditions import IsParameter
from atlas.parameters import Private

from threading import Thread
import requests
import time, os, logging

from dateutil.tz import tzlocal

import pandas as pd

def to_epoch(dt):
    # Hack as time.tzlocal() does not work for 1970-01-01
    if dt.tz:
        dt = dt.tz_convert("utc").tz_localize(None)
    return (dt - pd.Timestamp("1970-01-01")) // pd.Timedelta('1s')


@pytest.mark.parametrize(
    "make_tasks,query_url,expected_attrs",
    [
        pytest.param(
            lambda: [],
            "",
            {},
            id="No tasks"),
        pytest.param(
            lambda: [FuncTask(lambda: None, name="test-task", parameters={"x": 1, "y":2}, execution="main")],
            "",
            {
                "test-task": {
                    "name": "test-task", 
                    'func':'<lambda>', 
                    'execution':'main', 
                    "parameters": {"x": 1, "y": 2}, 
                    'status':None
                },
            },
            id="FuncTask, no filter"),
    ],
)
def test_tasks(client, make_tasks, query_url, expected_attrs):
    make_tasks()

    response = client.get("/tasks")
    data = response.get_json()

    assert expected_attrs.keys() == data.keys()

    for task, actual_attrs in data.items():
        for attr, expected in expected_attrs[task].items():
            assert expected == actual_attrs[attr]

    # Test not containing private attributes
    for task, actual_attrs in data.items():
        for attr in actual_attrs:
            assert not attr.startswith("_"), f"Attr {attr} is private"


@pytest.mark.parametrize(
    "params,query_url,expected",
    [
        pytest.param(
            {"mode": "test", "state": 1, "online": True, "stuff": [1,2,3], "subparams": {"x": 1}},
            "",
            {"mode": "test", "state": 1, "online": True, "stuff": [1,2,3], "subparams": {"x": 1}},
            id="No filter"),
        pytest.param(
            {"password": Private("123"), "user": "myname", "secrets": Private([1,2,3,4])},
            "",
            {"password": "*****", "user": "myname", "secrets": "*****"},
            id="No filter with private"),
    ],
)
def test_parameters(client, query_url, params, expected):
    session.parameters.update(params)
    response = client.get("/parameters" + query_url)
    data = response.get_json()

    assert expected == data


@pytest.mark.parametrize(
    "logs,query_url,expected_logs",
    [
        pytest.param(
            [
                ("2020-01-01 07:01:00", "run", "mytask"),
                ("2020-01-01 07:02:00", "success", "mytask"),
                ("2020-01-01 07:03:00", "run", "mytask"),
                ("2020-01-01 07:04:00", "terminate", "mytask"),
                ("2020-01-01 07:05:00", "run", "another task"),
                ("2020-01-01 07:06:00", "fail", "another task"),
            ],
            "",
            [
                ("2020-01-01 07:01:00", "run", "mytask"),
                ("2020-01-01 07:02:00", "success", "mytask"),
                ("2020-01-01 07:03:00", "run", "mytask"),
                ("2020-01-01 07:04:00", "terminate", "mytask"),
                ("2020-01-01 07:05:00", "run", "another task"),
                ("2020-01-01 07:06:00", "fail", "another task"),
            ],
            id="No filter"),

        pytest.param(
            [
                ("2020-01-01 07:01:00", "run", "mytask"),
                ("2020-01-01 07:02:00", "success", "mytask"),
                ("2020-01-01 07:03:00", "run", "mytask"),
                ("2020-01-01 07:04:00", "terminate", "mytask"),
                ("2020-01-01 07:05:00", "run", "another task"),
                ("2020-01-01 07:06:00", "fail", "another task"),
            ],
            "?action=run",
            [
                ("2020-01-01 07:01:00", "run", "mytask"),
                ("2020-01-01 07:03:00", "run", "mytask"),
                ("2020-01-01 07:05:00", "run", "another task"),
            ],
            id="Filter action"),

        pytest.param(
            [
                ("2020-01-01 07:01:00", "run", "mytask"),
                ("2020-01-01 07:02:00", "success", "mytask"),
                ("2020-01-01 07:03:00", "run", "mytask"),
                ("2020-01-01 07:04:00", "terminate", "mytask"),
                ("2020-01-01 07:05:00", "run", "another task"),
                ("2020-01-01 07:06:00", "fail", "another task"),
            ],
            "?action=run&action=success",
            [
                ("2020-01-01 07:01:00", "run", "mytask"),
                ("2020-01-01 07:02:00", "success", "mytask"),
                ("2020-01-01 07:03:00", "run", "mytask"),
                ("2020-01-01 07:05:00", "run", "another task"),
            ],
            id="Filter actions"),
        pytest.param(
            [
                ("2020-01-01 07:01:00", "run", "mytask"),
                ("2020-01-01 07:02:00", "success", "mytask"),
                ("2020-01-01 07:03:00", "run", "mytask"),
                ("2020-01-01 07:04:00", "terminate", "mytask"),
                ("2020-01-01 07:05:00", "run", "another task"),
                ("2020-01-01 07:06:00", "fail", "another task"),
            ],
            "?min_asctime=2020-01-01 07:01:30&max_asctime=2020-01-01 07:05:30",
            [
                ("2020-01-01 07:02:00", "success", "mytask"),
                ("2020-01-01 07:03:00", "run", "mytask"),
                ("2020-01-01 07:04:00", "terminate", "mytask"),
                ("2020-01-01 07:05:00", "run", "another task"),
            ],
            id="Filter asctime range"),
        pytest.param(
            [
                ("2020-01-01 07:01:00", "run", "mytask"),
                ("2020-01-01 07:02:00", "success", "mytask"),
                ("2020-01-01 07:03:00", "run", "mytask"),
                ("2020-01-01 07:04:00", "terminate", "mytask"),
                ("2020-01-01 07:05:00", "run", "another task"),
                ("2020-01-01 07:06:00", "fail", "another task"),
            ],
            "?min_asctime=2020-01-01 07:01:30",
            [
                ("2020-01-01 07:02:00", "success", "mytask"),
                ("2020-01-01 07:03:00", "run", "mytask"),
                ("2020-01-01 07:04:00", "terminate", "mytask"),
                ("2020-01-01 07:05:00", "run", "another task"),
                ("2020-01-01 07:06:00", "fail", "another task"),
            ],
            id="Filter asctime open right"),
        pytest.param(
            [
                ("2020-01-01 07:01:00", "run", "mytask"),
                ("2020-01-01 07:02:00", "success", "mytask"),
                ("2020-01-01 07:03:00", "run", "mytask"),
                ("2020-01-01 07:04:00", "terminate", "mytask"),
                ("2020-01-01 07:05:00", "run", "another task"),
                ("2020-01-01 07:06:00", "fail", "another task"),
            ],
            "?max_asctime=2020-01-01 07:05:30",
            [
                ("2020-01-01 07:01:00", "run", "mytask"),
                ("2020-01-01 07:02:00", "success", "mytask"),
                ("2020-01-01 07:03:00", "run", "mytask"),
                ("2020-01-01 07:04:00", "terminate", "mytask"),
                ("2020-01-01 07:05:00", "run", "another task"),
            ],
            id="Filter asctime open left"),

        pytest.param(
            [
                ("2020-01-01 07:02:00", "success", "mytask"),
                ("2020-01-01 07:03:00", "run", "mytask"),
                ("2020-01-01 07:04:00", "terminate", "mytask"),
            ],
            "?task_name=mytask&min_asctime=2020-01-01 07:01:30&action=success&action=terminate",
            [
                ("2020-01-01 07:02:00", "success", "mytask"),
                ("2020-01-01 07:04:00", "terminate", "mytask"),
            ],
            id="Multiple"),
    ],
)
def test_logs(client, logs, query_url, expected_logs):
    
    # A throwaway task for only forming the logger
    task = FuncTask(lambda: None)

    for log in logs:
        asctime, action, task_name = log
        log_created = to_epoch(pd.Timestamp(asctime, tz=tzlocal()))
        record = logging.LogRecord(
            # The content here should not matter for task status
            name='atlas.core.task.base', level=logging.INFO, lineno=1, 
            pathname='d:\\Projects\\atlas\\atlas\\core\\task\\base.py',
            msg="Logging of 'task'", args=(), exc_info=None,
        )

        record.created = log_created
        record.action = action
        record.task_name = task_name

        task.logger.handle(record)

    response = client.get("/logs/tasks" + query_url)
    data = response.get_json()

    actual_logs = [
        (rec["asctime"][:19], rec["action"], rec["task_name"]) 
        for rec in data
    ]
    assert expected_logs == actual_logs