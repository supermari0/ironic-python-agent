# Copyright 2013 Rackspace, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import abc
import functools
import operator
import os
import shlex

import netifaces
import psutil
import six
import stevedore

from ironic_python_agent import encoding
from ironic_python_agent import errors
from ironic_python_agent.openstack.common import log
from ironic_python_agent import utils

_global_manager = None


class HardwareSupport(object):
    """These are just guidelines to suggest values that might be returned by
    calls to `evaluate_hardware_support`. No HardwareManager in mainline
    ironic-python-agent will ever offer a value greater than `MAINLINE`.
    Service Providers should feel free to return values greater than
    SERVICE_PROVIDER to distinguish between additional levels of support.
    """
    NONE = 0
    GENERIC = 1
    MAINLINE = 2
    SERVICE_PROVIDER = 3


class HardwareType(object):
    MAC_ADDRESS = 'mac_address'


class BlockDevice(encoding.Serializable):
    serializable_fields = ('name', 'model', 'size', 'rotational')

    def __init__(self, name, model, size, rotational):
        self.name = name
        self.model = model
        self.size = size
        self.rotational = rotational


class NetworkInterface(encoding.Serializable):
    serializable_fields = ('name', 'mac_address', 'switch_port_descr',
                           'switch_chassis_descr')

    def __init__(self, name, mac_addr):
        self.name = name
        self.mac_address = mac_addr
        # TODO(russellhaering): Pull these from LLDP
        self.switch_port_descr = None
        self.switch_chassis_descr = None


class CPU(encoding.Serializable):
    serializable_fields = ('model_name', 'frequency', 'count')

    def __init__(self, model_name, frequency, count):
        self.model_name = model_name
        self.frequency = frequency
        self.count = count


class Memory(encoding.Serializable):
    serializable_fields = ('total', )

    def __init__(self, total):
        self.total = total


@six.add_metaclass(abc.ABCMeta)
class HardwareManager(object):
    # Version so we can restart the decommission process if it changes
    # between reboots
    HARDWARE_MANAGER_VERSION = '1'

    @abc.abstractmethod
    def evaluate_hardware_support(self):
        pass

    @abc.abstractmethod
    def list_network_interfaces(self):
        pass

    @abc.abstractmethod
    def get_cpus(self):
        pass

    @abc.abstractmethod
    def list_block_devices(self):
        pass

    @abc.abstractmethod
    def get_memory(self):
        pass

    @abc.abstractmethod
    def get_os_install_device(self):
        pass

    @abc.abstractmethod
    def erase_block_device(self, block_device):
        """Attempt to erase a block device.

        Implementations should detect the type of device and erase it in the
        most appropriate way possible.  Generic implementations should support
        common erase mechanisms such as ATA secure erase, or multi-pass random
        writes. Operators with more specific needs should override this method
        in order to detect and handle "interesting" cases, or delegate to the
        parent class to handle generic cases.

        For example: operators running ACME MagicStore (TM) cards alongside
        standard SSDs might check whether the device is a MagicStore and use a
        proprietary tool to erase that, otherwise call this method on their
        parent class. Upstream submissions of common functionality are
        encouraged.

        :param block_device: a BlockDevice indicating a device to be erased.
        :raises: BlockDeviceEraseError when an error occurs erasing a block
                 device, or if the block device is not supported.

        """
        pass

    @abc.abstractmethod
    def update_firmware(self, node, ports):
        pass

    @abc.abstractmethod
    def update_bios(self, node, ports):
        pass

    def get_decommission_steps(self):
        """Get a list of decommission steps with priority

        When deciding which steps to perform for a decommission, the agent will
        run each step in this list, in order of priority (starting at 1). If a
        steps' priority is None, it will not be run. A step with priority None
        can only be called by via the API if the

        Returns a list of dicts of the following form:
        {'function': the HardwareManager function to call.
         'priority': the order to call, starting at 1. If two steps share
                    the same priority, their order is undefined. Set to None
                    to not run during normal decommission.
         'reboot_requested': Whether the agent should request Ironic reboots
                             it after the operation completes.
         'state': The state the machine will be in when the operation
                  completes. This will match the decommission_target_state
                  saved in the Ironic node.
        :return: a default list of decommission steps, as a list of
        dictionaries
        """
        return [
            {
                'state': 'update_bios',
                'function': 'update_bios',
                'priority': 10,
                'reboot_requested': False,
            },
            {
                'state': 'update_firmware',
                'function': 'update_firmware',
                'priority': 20,
                'reboot_requested': False,
            },
            {
                'state': 'erase_devices',
                'function': 'erase_devices',
                'priority': 30,
                'reboot_requested': False,
            },
            {
                'state': 'verify_properties',
                'function': 'verify_properties',
                'priority': 40,
                'reboot_requested': False,
            }
        ]

    def erase_devices(self, driver_info):
        """Erase any device that holds user data.

        By default this will attempt to erase block devices. This method can be
        overridden in an implementation-specific hardware manager in order to
        erase additional hardware, although backwards-compatible upstream
        submissions are encouraged.
        """
        block_devices = self.list_block_devices()
        for block_device in block_devices:
            self.erase_block_device(block_device)

    def decommission(self, node, ports, **kwargs):
        """Run through a multi stage decommission process

        :param node: A dict representation of an Ironic node to decommission.
                    The driver info from the Ironic Node to be decommissioned.
                    Needs to contain a key 'decommission_target_state' with
                    the next decommission state to move to.
        :param ports: A list of dict representations of the Port objects
                      attached to the node.
        :param kwargs: May contain a key 'decommission_target_state' that will
                       run the specified state instead of the next state in
                       get_decommission_steps.
        :return: A dict containing 'decommission_next_state',
                 'reboot_requested', 'hardware_manager_version' and
                 'step_return_value'
        """
        driver_info = node.get('driver_info', {})
        target_state = kwargs.get('decommission_target_state')
        decommission_steps = self.get_decommission_steps()

        if not target_state:
            if 'decommission_target_state' not in driver_info:
                raise errors.DecommissionError('Node object requires key '
                                               '"decommission_target_state".')
            target_state = driver_info.get('decommission_target_state')
            # Sort and filter the steps
            steps = _get_sorted_steps(decommission_steps)
        else:
            # If specifying a specific state, don't filter or sort
            steps = decommission_steps

        node_version = driver_info.get('hardware_manager_version')
        # If versions are not the same, request restart of decommission process
        # If node_version is not set, it's the first run, can't be a mismatch
        if node_version and node_version != self.HARDWARE_MANAGER_VERSION:
            raise errors.WrongDecommissionVersion(
                agent_version=self.HARDWARE_MANAGER_VERSION,
                node_version=node_version)

        if not target_state:
            # If no previous step, use the first sorted step
            step = steps[0]
        else:
            # Run the command matching target state
            step = None
            for decommission_step in steps:
                if decommission_step.get('state') == target_state:
                    step = decommission_step
                    break
        if step is None:
            raise errors.DecommissionError(
                'Hardware manager does not have %s as an available state.'
                % target_state)

        # Get the function from the hardware manager
        try:
            func = getattr(self, step['function'])
        except AttributeError:
            raise errors.DecommissionError(
                'Hardware manager does not have %s as a function.' %
                step['function'])

        # Execute function
        try:
            #TODO(JoshNang) return the result to commandresult
            return_value = func(node, ports)
        except Exception as e:
            raise errors.DecommissionError(
                'Error performing decommission function %(step)s: %(err)s' %
                {'step': step['function'], 'err': str(e)})

        return self._get_next_target_state(decommission_steps, step,
                                           return_value)

    def _get_next_target_state(self, decommission_steps, step, return_value):
        """Given the current state, determine the next decommission state."""
        next_steps = _get_sorted_steps(decommission_steps)
        for index, next_step in enumerate(next_steps):
            if next_step['state'] == step['state']:
                if index == len(next_steps) - 1:
                    next_state = 'DONE'
                else:
                    next_state = next_steps[index + 1]['state']
                return {
                    # This will get saved in Node.driver_info[
                    # 'target_decommission_state'] and sent back to the node
                    # on lookup
                    'decommission_next_state': next_state,
                    # If true, the node will be rebooted by Ironic
                    # (possibly out of band)
                    'reboot_requested': step.get('reboot_requested'),
                    # The output from the last run command
                    'step_return_value': return_value,
                    # The current hardware manager version
                    'hardware_manager_version': self.HARDWARE_MANAGER_VERSION
                }

    def list_hardware_info(self):
        hardware_info = {}
        hardware_info['interfaces'] = self.list_network_interfaces()
        hardware_info['cpu'] = self.get_cpus()
        hardware_info['disks'] = self.list_block_devices()
        hardware_info['memory'] = self.get_memory()
        return hardware_info


class GenericHardwareManager(HardwareManager):
    HARDWARE_MANAGER_VERSION = '1'

    def __init__(self):
        self.sys_path = '/sys'

        if os.path.isdir('/mnt/sys'):
            self.sys_path = '/mnt/sys'

    def evaluate_hardware_support(self):
        return HardwareSupport.GENERIC

    def _get_interface_info(self, interface_name):
        addr_path = '{0}/class/net/{1}/address'.format(self.sys_path,
                                                     interface_name)
        with open(addr_path) as addr_file:
            mac_addr = addr_file.read().strip()

        return NetworkInterface(interface_name, mac_addr)

    def get_ipv4_addr(self, interface_id):
        try:
            addrs = netifaces.ifaddresses(interface_id)
            return addrs[netifaces.AF_INET][0]['addr']
        except (ValueError, IndexError, KeyError):
            # No default IPv4 address found
            return None

    def _is_device(self, interface_name):
        device_path = '{0}/class/net/{1}/device'.format(self.sys_path,
                                                      interface_name)
        return os.path.exists(device_path)

    def list_network_interfaces(self):
        iface_names = os.listdir('{0}/class/net'.format(self.sys_path))
        return [self._get_interface_info(name)
                for name in iface_names
                if self._is_device(name)]

    def _get_cpu_count(self):
        if psutil.version_info[0] == 1:
            return psutil.NUM_CPUS
        elif psutil.version_info[0] == 2:
            return psutil.cpu_count()
        else:
            raise AttributeError("Only psutil versions 1 and 2 supported")

    def get_cpus(self):
        model = None
        freq = None
        with open('/proc/cpuinfo') as f:
            lines = f.read()
            for line in lines.split('\n'):
                if model and freq:
                    break
                if not model and line.startswith('model name'):
                    model = line.split(':')[1].strip()
                if not freq and line.startswith('cpu MHz'):
                    freq = line.split(':')[1].strip()

        return CPU(model, freq, self._get_cpu_count())

    def get_memory(self):
        # psutil returns a long, so we force it to an int
        if psutil.version_info[0] == 1:
            return Memory(int(psutil.TOTAL_PHYMEM))
        elif psutil.version_info[0] == 2:
            return Memory(int(psutil.phymem_usage().total))

    def list_block_devices(self):
        """List all physical block devices

        The switches we use for lsblk: P for KEY="value" output,
        b for size output in bytes, d to exclude dependant devices
        (like md or dm devices), i to ensure ascii characters only,
        and  o to specify the fields we need

        :return: A list of BlockDevices
        """
        report = utils.execute('lsblk', '-PbdioKNAME,MODEL,SIZE,ROTA,TYPE',
                               check_exit_code=[0])[0]
        lines = report.split('\n')

        devices = []
        for line in lines:
            device = {}
            # Split into KEY=VAL pairs
            vals = shlex.split(line)
            for key, val in (v.split('=', 1) for v in vals):
                device[key] = val.strip()
            # Ignore non disk
            if device.get('TYPE') != 'disk':
                continue

            # Ensure all required keys are at least present, even if blank
            diff = set(['KNAME', 'MODEL', 'SIZE', 'ROTA']) - set(device.keys())
            if diff:
                raise errors.BlockDeviceError(
                    '%s must be returned by lsblk.' % diff)
            devices.append(BlockDevice(name='/dev/' + device['KNAME'],
                                       model=device['MODEL'],
                                       size=int(device['SIZE']),
                                       rotational=bool(int(device['ROTA']))))
        return devices

    def get_os_install_device(self):
        # Find the first device larger than 4GB, assume it is the OS disk
        # TODO(russellhaering): This isn't a valid assumption in all cases,
        #                       is there a more reasonable default behavior?
        block_devices = self.list_block_devices()
        block_devices.sort(key=lambda device: device.size)
        for device in block_devices:
            if device.size >= (4 * pow(1024, 3)):
                return device.name

    def erase_block_device(self, block_device):
        if self._ata_erase(block_device):
            return

        # NOTE(russell_h): Support for additional generic erase methods should
        # be added above this raise, in order of precedence.
        raise errors.BlockDeviceEraseError(('Unable to erase block device '
            '{0}: device is unsupported.').format(block_device.name))

    def _get_ata_security_lines(self, block_device):
        output = utils.execute('hdparm', '-I', block_device.name)[0]

        if '\nSecurity: ' not in output:
            return []

        # Get all lines after the 'Security: ' line
        security_and_beyond = output.split('\nSecurity: \n')[1]
        security_and_beyond_lines = security_and_beyond.split('\n')

        security_lines = []
        for line in security_and_beyond_lines:
            if line.startswith('\t'):
                security_lines.append(line.strip().replace('\t', ' '))
            else:
                break

        return security_lines

    def _ata_erase(self, block_device):
        security_lines = self._get_ata_security_lines(block_device)

        # If secure erase isn't supported return False so erase_block_device
        # can try another mechanism. Below here, if secure erase is supported
        # but fails in some way, error out (operators of hardware that supports
        # secure erase presumably expect this to work).
        if 'supported' not in security_lines:
            return False

        if 'enabled' in security_lines:
            raise errors.BlockDeviceEraseError(('Block device {0} already has '
                'a security password set').format(block_device.name))

        if 'not frozen' not in security_lines:
            raise errors.BlockDeviceEraseError(('Block device {0} is frozen '
                'and cannot be erased').format(block_device.name))

        utils.execute('hdparm', '--user-master', 'u', '--security-set-pass',
                      'NULL', block_device.name, check_exit_code=[0])
        utils.execute('hdparm', '--user-master', 'u', '--security-erase',
                      'NULL', block_device.name, check_exit_code=[0])

        # Verify that security is now 'not enabled'
        security_lines = self._get_ata_security_lines(block_device)
        if 'not enabled' not in security_lines:
            raise errors.BlockDeviceEraseError(('An unknown error occurred '
                'erasing block device {0}').format(block_device.name))

        return True

    def update_bios(self, node, ports):
        pass

    def update_firmware(self, node, ports):
        pass

    def verify_properties(self, node, ports=None):
        """Verify that the node's properties match the hardware
        :param node: a dict representation of the node
        :param ports: a list of dict representation of Ports connected to
                      the node
        """
        properties = node.get('properties', {})
        hardware = self.list_hardware_info()
        # Ensure possibly overridden list_hardware_info return correct results
        for key in ('cpu', 'memory', 'disks'):
            if not hardware.get(key):
                raise errors.VerificationError(
                    'list_hardware_info needs to return cpu, memory and '
                    'disks keys')
        self._verify_cpu_count(properties, hardware)
        self._verify_memory_size(properties, hardware)
        self._verify_disks_size(properties, hardware)

    def _verify_cpu_count(self, properties, hardware):
        """Verifies CPU count is the same as listed in node.properties."""
        given = hardware['cpu'].count
        actual = properties.get('cpus', 0)

        if given != actual:
            raise errors.VerificationFailed(
                'Node CPU count %(given)s does not match detected count '
                '%(actual)s' % {'given': given, 'actual': actual})

    def _verify_memory_size(self, properties, hardware):
        """Verifies memory size is the same as listed in node.properties."""
        # Convert bytes to MB
        given = hardware['memory'].total / (1024 * 1024)
        actual = properties.get('memory_mb', 0)

        if given != actual:
            raise errors.VerificationFailed(
                'Node memory size %(given)s does not match detected '
                'count %(actual)s' % {'given': given, 'actual': actual})

    def _verify_disks_size(self, properties, hardware):
        """Verifies disk size is the same as listed in node.properties."""
        actual = properties.get('local_gb', 0)
        # TODO(JoshNang) fix listing hardware twice
        name = self.get_os_install_device()
        disk = None
        for device in hardware['disks']:
            if device.name == name:
                disk = device
                break

        # Make sure not to skip if this is a diskless system
        if not disk and actual > 0:
            raise errors.VerificationFailed(
                'Could not find a disk to match to local_gb.')
        # Convert bytes to GB

        given = disk.size / (1024 * 1024 * 1024)
        if given != actual:
            raise errors.VerificationFailed(
                'Node disk size %(given)s does not match detected '
                'size %(actual)s' % {'given': given, 'actual': actual})


def _get_sorted_steps(steps):
    """Sort decommission steps by priority."""
    return [x for x in sorted(steps, key=operator.itemgetter('priority'))
            if x['priority'] is not None]


def _compare_extensions(ext1, ext2):
    mgr1 = ext1.obj
    mgr2 = ext2.obj
    return mgr2.evaluate_hardware_support() - mgr1.evaluate_hardware_support()


def get_manager():
    global _global_manager

    if not _global_manager:
        LOG = log.getLogger()
        extension_manager = stevedore.ExtensionManager(
            namespace='ironic_python_agent.hardware_managers',
            invoke_on_load=True)

        # There will always be at least one extension available (the
        # GenericHardwareManager).
        if six.PY2:
            preferred_extension = sorted(
                    extension_manager,
                    _compare_extensions)[0]
        else:
            preferred_extension = sorted(
                    extension_manager,
                    key=functools.cmp_to_key(_compare_extensions))[0]

        preferred_manager = preferred_extension.obj

        if preferred_manager.evaluate_hardware_support() <= 0:
            raise RuntimeError('No suitable HardwareManager could be found')

        LOG.info('selected hardware manager {0}'.format(
                 preferred_extension.entry_point_target))

        _global_manager = preferred_manager

    return _global_manager
