#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
for ansible 2.8
'''
import os
import tempfile
from collections import namedtuple
from ansible.parsing.dataloader import DataLoader
from ansible.vars.manager import VariableManager
from ansible.inventory.manager import InventoryManager
from ansible.playbook.play import Play
from ansible.executor.playbook_executor import PlaybookExecutor
from ansible.executor.task_queue_manager import TaskQueueManager
from ansible.plugins.callback import CallbackBase
from optparse import Values
from ansible import context
from ansible.module_utils.common.collections import ImmutableDict


class AnsibleHost:
    def __init__(self, host, port=None, connection=None, ssh_user=None, ssh_pass=None):
        self.host = host
        self.port = port
        self.ansible_connection = connection
        self.ansible_ssh_user = ssh_user
        self.ansible_ssh_pass = ssh_pass

    def __str__(self):
        result = str(self.host)+' '+'ansible_ssh_host=' + str(self.host)
        if self.port:
            result += ' ansible_ssh_port=' + str(self.port)
        if self.ansible_connection:
            result += ' ansible_connection=' + str(self.ansible_connection)
        if self.ansible_ssh_user:
            result += ' ansible_ssh_user=' + str(self.ansible_ssh_user)
        if self.ansible_ssh_pass:
            result += ' ansible_ssh_pass=' + "'" + \
                str(self.ansible_ssh_pass) + "'"
        return result

    __repr__ = __str__  # 这样不会返回实例，调用了__str__函数


class AnsibleTaskResultCallback(CallbackBase):
    """
       playbook的callback改写，格式化输出playbook执行结果
       """
    CALLBACK_VERSION = 2.0

    def __init__(self, *args, **kwargs):
        super(AnsibleTaskResultCallback, self).__init__(*args, **kwargs)
        self.task_ok = {}
        self.task_unreachable = {}
        self.task_failed = {}
        self.task_skipped = {}
        self.result = None

    def v2_runner_on_unreachable(self, result):
        """
        重写 unreachable 状态
        :param result:  这是父类里面一个对象，这个对象可以获取执行任务信息
        """
        self.task_unreachable[result._host.get_name()] = result

    def v2_runner_on_ok(self, result, *args, **kwargs):
        """
        重写 ok 状态
        :param result:
        """
        self.task_ok[result._host.get_name()] = result

    def v2_runner_on_failed(self, result, *args, **kwargs):
        """
        重写 failed 状态
        :param result:
        """
        self.task_failed[result._host.get_name()] = result

    def v2_runner_on_skipped(self, result):
        self.task_skipped[result._host.get_name()] = result


class AnsibleTask:
    def __init__(self, hosts, extra_vars=None):
        self.hosts = hosts
        self._validate()
        self.hosts_file = None
        self._generate_hosts_file()

        # 资产配置信息
        self.loader = DataLoader()  # 读取 json/ymal/ini 格式的文件的数据解析器
        self.passwords = dict(vault_pass='secret')

        self.inventory = InventoryManager(loader=self.loader, sources=[
                                          self.hosts_file])  # 管理资源库的，可以指定一个 inventory 文件等
        self.variable_manager = VariableManager(
            loader=self.loader, inventory=self.inventory)  # 管理主机和主机组的变量管理器
        if extra_vars:
            self.variable_manager.extra_vars
        # Ansible自己封装了一个ImmutableDict ，之后需要和context结合使用的
        self.options = {'verbosity': 0, 'ask_pass': False, 'private_key_file': None, 'remote_user': None,
                        'connection': 'smart', 'timeout': 10, 'ssh_common_args': '', 'sftp_extra_args': '',
                        'scp_extra_args': '', 'ssh_extra_args': '', 'force_handlers': False, 'flush_cache': None,
                        'become': False, 'become_method': 'sudo', 'become_user': None, 'become_ask_pass': False,
                        'tags': ['all'], 'skip_tags': [], 'check': False, 'syntax': None, 'diff': False,
                        'listhosts': None, 'subset': None, 'extra_vars': [], 'ask_vault_pass': False,
                        'vault_password_files': [], 'vault_ids': [], 'forks': 5, 'module_path': None,
                        'listtasks': None,
                        'listtags': None, 'step': None, 'start_at_task': None, 'args': ['fake']}
        self.ops = Values(self.options)

    def _generate_hosts_file(self):
        self.hosts_file = tempfile.mktemp()
        with open(self.hosts_file, 'w+') as file:
            hosts = []
            for host in self.hosts:
                hosts.append(str(host))
            file.write('\n'.join(hosts))

    def _validate(self):
        if not self.hosts:
            raise Exception('hosts不能为空')
        if not isinstance(self.hosts, list):
            raise Exception('hosts只能为list<AnsibleHost>数组')
        for host in self.hosts:
            if not isinstance(host, AnsibleHost):
                raise Exception('host类型必须为AnsibleHost')

    def exec_shell(self, command):
        source = {'hosts': 'all', 'gather_facts': 'no', 'tasks': [
            {'action': {'module': 'shell', 'args': command},
             'register': 'shell_out'}]}  # # create data structure that represents our play这里修改模块名 如果是copy的话  args可以是src=ansible-excute.py dest=/tmp
        # Create play object, playbook objects use .load instead of init or new methods,
        # this will also automatically create the task objects from the info provided in play_source
        play = Play().load(source, variable_manager=self.variable_manager, loader=self.loader)
        # Instantiate our ResultCallback for handling results as they come in
        results_callback = AnsibleTaskResultCallback()
        tqm = None
        try:
            tqm = TaskQueueManager(
                inventory=self.inventory,
                variable_manager=self.variable_manager,
                loader=self.loader,
                passwords=self.passwords,
                stdout_callback=results_callback
            )
            tqm.run(play)
            result_raw = {"ok": {}, "failed": {},
                          "unreachable": {}, "skipped": {}}
            for host, result in results_callback.task_ok.items():
                result_raw["ok"][host] = result._result

            for host, result in results_callback.task_failed.items():
                result_raw["failed"][host] = result._result

            for host, result in results_callback.task_unreachable.items():
                result_raw["unreachable"][host] = result._result

            for host, result in results_callback.task_skipped.items():
                result_raw["skipped"][host] = result._result

            return result_raw
        except:
            raise
        finally:
            if tqm is not None:
                tqm.cleanup()

    def exec_playbook(self, playbooks):
        context._init_global_context(self.ops)

        playbook = PlaybookExecutor(playbooks=playbooks,
                                    inventory=self.inventory,
                                    variable_manager=self.variable_manager,
                                    loader=self.loader, passwords=self.passwords)
        results_callback = AnsibleTaskResultCallback()
        playbook._tqm._stdout_callback = results_callback
        result = playbook.run()
        result_raw = {"ok": {}, "failed": {},
                      "unreachable": {}, "skipped": {}}
        for host, result in results_callback.task_ok.items():
            result_raw["ok"][host] = result._result

        for host, result in results_callback.task_failed.items():
            result_raw["failed"][host] = result._result

        for host, result in results_callback.task_unreachable.items():
            result_raw["unreachable"][host] = result._result

        for host, result in results_callback.task_skipped.items():
            result_raw["skipped"][host] = result._result

        return result_raw

    def __del__(self):  # 删除对象的时候默认调用的方法
        if self.hosts_file:
            os.remove(self.hosts_file)

if __name__ == "__main__":
    hosts = [['ip', 22, 'ssh', 'root', 'password']]
    hosts_arry = []
    for i in hosts:
        hosts_arry.append(AnsibleHost(i[0], i[1], i[2], i[3], i[4]))
    task = AnsibleTask(hosts_arry)
    result = task.exec_playbook(['test.yml'])
    if result['ok']:
        print("play success")