

"""
Utilities for getting information 
about the scehuler/task/parameters etc.
"""

import logging
from typing import List, Dict, Union
from pathlib import Path
from itertools import chain
import pandas as pd

from powerbase.core.log import TaskAdapter
from powerbase.core import Scheduler, Task, BaseCondition, Parameters
from powerbase.core import conditions

from powerbase.log import CsvHandler, CsvFormatter
from powerbase.config import get_default, DEFAULT_BASENAME_TASKS, DEFAULT_BASENAME_SCHEDULER
import powerbase

_BASE_CONDITIONS = {cls.__name__: cls for cls in (conditions.All, conditions.Any, conditions.AlwaysTrue, conditions.AlwaysFalse)}

class Session:
    """Collection of the relevant data and methods
    of the powerbase ecosystem. 

    """

    tasks: dict
    config: dict
    parameters: Parameters
    scheduler: Scheduler

    task_cls: dict
    cond_cls: dict

    default_config = {
        "use_instance_naming": False, # Whether to use id(task) as task.name if name not specified
        "task_pre_exist": "raise", # What to do if a task name is already taken
        "force_status_from_logs": False, # Force to check status from logs every time (slow but robust)
        "task_logger_basename": DEFAULT_BASENAME_TASKS,
        "scheduler_logger_basename": DEFAULT_BASENAME_SCHEDULER,

        "session_store_cond_cls": True,
        "session_store_task_cls": True,
        "debug": False,
    }

    def __init__(self, config:dict=None, tasks:dict=None, parameters:Parameters=None, scheme:Union[str,list]=None):
        # Set defaults
        config = {} if config is None else config
        tasks = {} if tasks is None else tasks
        parameters = (
            Parameters() if parameters is None 
            else Parameters(parameters) if not isinstance(parameters, Parameters)
            else parameters
        )

        # Set attrs
        self.config = self.default_config.copy()
        self.config.update(config)

        self.tasks = tasks
        self.parameters = parameters

        self.cond_cls = self.cond_cls.copy()
        self.task_cls = self.task_cls.copy()

        self.scheduler = None
        if scheme is not None:
            is_list_of_schemes = not isinstance(scheme, str)
            if is_list_of_schemes:
                for sch in scheme:
                    self.set_scheme(sch)
            else:
                self.set_scheme(scheme)

    def set_scheme(self, scheme:str):
        scheduler_basename = self.config["scheduler_logger_basename"]
        task_basename = self.config["task_logger_basename"]
        get_default(scheme, scheduler_basename=scheduler_basename, task_basename=task_basename)

    def start(self):
        """Start the scheduling session.

        Will block and wait till the scheduler finishes 
        (if has shutdown condition)"""
        self.scheduler()

    def get_tasks(self) -> list:
        return self.tasks.values()

    def get_task(self, task):
        return self.tasks[task] if not isinstance(task, Task) else task

    def get_task_loggers(self, with_adapters=True) -> dict:
        basename = self.config["task_logger_basename"]
        return {
            # The adapter should not be used to log (but to read) thus task_name = None
            name: TaskAdapter(logger, None) if with_adapters else logger 
            for name, logger in logging.root.manager.loggerDict.items() 
            if name.startswith(basename) 
            and not isinstance(logger, logging.PlaceHolder)
            and not name.endswith("_process") # No private
        }

    def get_scheduler_loggers(self, with_adapters=True) -> dict:
        basename = self.config["scheduler_logger_basename"]
        return {
            # The adapter should not be used to log (but to read) thus task_name = None
            name: TaskAdapter(logger, None) if with_adapters else logger  
            for name, logger in logging.root.manager.loggerDict.items() 
            if name.startswith(basename) 
            and not isinstance(logger, logging.PlaceHolder)
            and not name.startswith("_") # No private
        }

# Log data
    def get_task_log(self, **kwargs) -> List[Dict]:
        loggers = self.get_task_loggers(with_adapters=True)
        data = iter(())
        for logger in loggers.values():
            data = chain(data, logger.get_records(**kwargs))
        return data

    def get_scheduler_log(self, **kwargs) -> List[Dict]:
        loggers = self.get_scheduler_loggers(with_adapters=True)
        data = iter(())
        for logger in loggers.values():
            data = chain(data, logger.get_records(**kwargs))
        return data

    def get_task_info(self):
        return pd.DataFrame([
            {
                "name": name, 
                "priority": task.priority, 
                "timeout": task.timeout, 
                "start_condition": task.start_cond, 
                "end_condition": task.end_cond
            } for name, task in session.get_tasks().items()
        ])

    def reset(self):
        "Set Pypipe ecosystem to default settings (clearing tasks etc)"

        # Clear stuff
        self.tasks = {}
        self.parameters = Parameters()

        # Set default settings
        Task.use_instance_naming = False
        get_default("csv_logging")
        
    def clear(self):
        "Clear tasks, parameters etc. of the session"
        self.tasks = {}
        self.parameters = Parameters()
        self.scheduler = None

    def __getstate__(self):
        # NOTE: When a process task is executed, it will pickle
        # the task.session. Therefore removing unpicklable here.
        state = self.__dict__.copy()
        state["tasks"] = {}
        state["scheduler"] = None
        return state

    @property
    def env(self):
        "Shorthand for parameter 'env'"
        return self.parameters.get("env")

    @env.setter
    def env(self, value):
        "Shorthand for parameter 'env'"
        self.parameters["env"] = value

    def set_as_default(self):
        """Set this session as default session for 
        next tasks, conditions and schedulers that
        are created."""
        Scheduler.session = self
        Task.session = self
        BaseCondition.session = self
        Parameters.session = self
        powerbase.session = self