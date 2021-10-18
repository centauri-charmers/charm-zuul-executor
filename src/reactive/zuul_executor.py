import base64
import subprocess
import yaml

import charms.reactive as reactive
# import reactive.helpers
import charms.reactive.relations as relations

import charmhelpers.core as ch_core
import charmhelpers.core.host as ch_host
import charmhelpers.core.templating as templating
import charmhelpers.core.hookenv as hookenv
# from charmhelpers.core.hookenv import log


@reactive.when('apt.installed.libre2-dev', 'apt.installed.python3-pip')
@reactive.when_not('zuul.installed')
def install_zuul():
    subprocess.check_call(['/usr/bin/pip3', 'install', 'zuul<4'])
    reactive.set_flag('zuul.installed')


@reactive.when('zuul.installed')
@reactive.when_not('endpoint.zookeeper.joined')
def connect_zookeeper():
    hookenv.status_set('blocked', 'Relate Zookeeper to continue')


@reactive.when('zuul.installed', 'endpoint.zookeeper.joined')
@reactive.when_not('endpoint.zookeeper.available')
def wait_for_zookeeper():
    hookenv.status_set('waiting', 'Waiting for Zookeeper to become available')


@reactive.when('endpoint.zookeeper.available')
@reactive.when_not('shared-db.connected')
def wait_for_db():
    hookenv.status_set('blocked', 'Relate database to continue')


@reactive.when('shared-db.connected')
@reactive.when_not('shared-db.available')
def setup_database(database):
    database.configure('zuul', 'zuul')
    hookenv.status_set('waiting', 'Waiting for database to become available')


@reactive.when('shared-db.available')
@reactive.when_not('endpoint.gearman.available')
def setup_gearman():
    hookenv.status_set(
        'waiting', 'Relate Gearman / zuul-scheduler to continue')


@reactive.when_any('config.changed.connections',
                   'endpoint.zookeeper.changed',)
def reset_configured():
    reactive.clear_flag('zuul.configured')


@reactive.when('zuul.user.created',
               'config.set.ssh_key',)
def configure_ssh_key():
    key = base64.b64decode(hookenv.config().get('ssh_key', ''))
    ch_host.mkdir('/var/lib/zuul/.ssh/', owner='zuul',
                  group='zuul', perms=0o700)
    ch_host.write_file('/var/lib/zuul/.ssh/id_rsa', content=key, owner='zuul',
                       group='zuul', perms=0o600)


@reactive.when('zuul.installed',
               'endpoint.zookeeper.available',
               'shared-db.available',
               'endpoint.gearman.available',
               'zuul.user.created')
@reactive.when_not('zuul.configured')
def configure():
    zookeeper = relations.endpoint_from_flag('endpoint.zookeeper.available')
    mysql = relations.endpoint_from_flag('shared-db.available')
    gearman = relations.endpoint_from_flag('endpoint.gearman.available')
    connections = []
    try:
        connections_yaml = hookenv.config().get('connections')
        if connections_yaml:
            connections = yaml.safe_load(connections_yaml)
    except yaml.YAMLError:
        pass
    conf = {
        'zk_servers': [],
        'connections': connections,
        'database': mysql,
        'git_username': hookenv.config().get('git_username'),
        'git_email': hookenv.config().get('git_email'),
        'gearman_server': gearman.address(),
        'executor_disk_limit': hookenv.config().get(
            'executor_disk_limit', '-1'),
        'public_ip': hookenv.unit_public_ip(),
    }
    for zk_unit in zookeeper.list_unit_data():
        conf['zk_servers'].append(
            "{}:{}".format(zk_unit['host'].replace('"', ''), zk_unit['port']))
    templating.render(
        'zuul.conf', '/etc/zuul/zuul.conf',
        context=conf, perms=0o650, group='zuul', owner='zuul')
    if reactive.helpers.any_file_changed(['/etc/zuul/zuul.conf']):
        reactive.set_flag('service.zuul.restart')
        reactive.set_flag('zuul.configured')


@reactive.when('service.zuul.restart')
def restart_services():
    ch_core.host.service_restart('zuul-executor')


@reactive.when_not('zuul.user.created')
def add_zuul_user():
    subprocess.check_call(["groupadd", "--system", "zuul"])
    subprocess.check_call([
        'useradd', '--system', 'zuul',
        '--home-dir', '/var/lib/zuul', '--create-home',
        '-g', 'zuul'])
    reactive.set_flag('zuul.user.created')


@reactive.when('zuul.configured', 'zuul.user.created')
@reactive.when_not('zuul-executor.started')
def enable_executor():
    templating.render(
        'zuul-executor.service', '/etc/systemd/system/zuul-executor.service',
        context={})
    ch_core.host.service_resume('zuul-executor')
    reactive.set_flag('zuul-executor.started')


@reactive.when('zuul-executor.started',)
def set_ready():
    hookenv.status_set('active', 'Zuul is ready')
