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

import mock
from oslotest import base as test_base
import six

from ironic_python_agent import errors
from ironic_python_agent.extensions import standby
from ironic_python_agent.openstack.common import processutils

if six.PY2:
    OPEN_FUNCTION_NAME = '__builtin__.open'
else:
    OPEN_FUNCTION_NAME = 'builtins.open'


class TestStandbyExtension(test_base.BaseTestCase):
    def setUp(self):
        super(TestStandbyExtension, self).setUp()
        self.agent_extension = standby.StandbyExtension()

    def _build_fake_image_info(self):
        return {
            'id': 'fake_id',
            'urls': [
                'http://example.org',
            ],
            'checksum': 'abc123'
        }

    def test_validate_image_info_success(self):
        standby._validate_image_info(None, self._build_fake_image_info())

    def test_validate_image_info_missing_field(self):
        for field in ['id', 'urls', 'checksum']:
            invalid_info = self._build_fake_image_info()
            del invalid_info[field]

            self.assertRaises(errors.InvalidCommandParamsError,
                              standby._validate_image_info,
                              invalid_info)

    def test_validate_image_info_invalid_urls(self):
        invalid_info = self._build_fake_image_info()
        invalid_info['urls'] = 'this_is_not_a_list'

        self.assertRaises(errors.InvalidCommandParamsError,
                          standby._validate_image_info,
                          invalid_info)

    def test_validate_image_info_empty_urls(self):
        invalid_info = self._build_fake_image_info()
        invalid_info['urls'] = []

        self.assertRaises(errors.InvalidCommandParamsError,
                          standby._validate_image_info,
                          invalid_info)

    def test_validate_image_info_invalid_checksum(self):
        invalid_info = self._build_fake_image_info()
        invalid_info['checksum'] = {'not': 'a string'}

        self.assertRaises(errors.InvalidCommandParamsError,
                          standby._validate_image_info,
                          invalid_info)

    def test_validate_image_info_empty_checksum(self):
        invalid_info = self._build_fake_image_info()
        invalid_info['checksum'] = ''

        self.assertRaises(errors.InvalidCommandParamsError,
                          standby._validate_image_info,
                          invalid_info)

    def test_cache_image_invalid_image_list(self):
        self.assertRaises(errors.InvalidCommandParamsError,
                          self.agent_extension.cache_image,
                          image_info={'foo': 'bar'})

    def test__write_image(self):
        image_info = self._build_fake_image_info()
        device = '/dev/sda'
        img_mgr_mock = mock.Mock()

        self.assertEqual(None, self.agent_extension.cached_image_id)

        self.agent_extension._write_image(img_mgr_mock,
                                          image_info,
                                          device)

        self.assertEqual(image_info['id'],
                         self.agent_extension.cached_image_id)
        img_mgr_mock.write_os_image.assert_called_once_with(
                image_info, device)

    def test__write_image_already_cached(self):
        image_info = self._build_fake_image_info()
        device = '/dev/sda'
        img_mgr_mock = mock.Mock()

        self.agent_extension.cached_image_id = image_info['id']

        self.agent_extension._write_image(img_mgr_mock,
                                          image_info,
                                          device)

        self.assertEqual(image_info['id'],
                         self.agent_extension.cached_image_id)
        self.assertFalse(img_mgr_mock.write_os_image.called)

    def test__write_image_already_cached_force(self):
        image_info = self._build_fake_image_info()
        device = '/dev/sda'
        img_mgr_mock = mock.Mock()

        self.agent_extension.cached_image_id = image_info['id']

        self.agent_extension._write_image(img_mgr_mock,
                                          image_info,
                                          device,
                                          force=True)

        self.assertEqual(image_info['id'],
                         self.agent_extension.cached_image_id)
        img_mgr_mock.write_os_image.assert_called_once_with(
                image_info, device)

    @mock.patch.object(standby.StandbyExtension, '_write_image')
    @mock.patch('ironic_python_agent.hardware.get_manager', autospec=True)
    def test_cache_image(self, hardware_mock, write_mock):
        image_info = self._build_fake_image_info()
        hw_mgr_mock = hardware_mock.return_value
        hw_mgr_mock.get_os_install_device.return_value = 'boot_device'
        hw_mgr_mock.get_image_manager.return_value = 'img_mgr'

        async_result = self.agent_extension.cache_image(image_info=image_info)
        async_result.join()
        write_mock.assert_called_once_with('img_mgr', image_info,
                                           'boot_device', force=False)
        self.assertEqual('SUCCEEDED', async_result.command_status)
        self.assertEqual(None, async_result.command_result)

    @mock.patch.object(standby.StandbyExtension, '_write_image')
    @mock.patch('ironic_python_agent.hardware.get_manager', autospec=True)
    def test_cache_image_force(self, hardware_mock, write_mock):
        image_info = self._build_fake_image_info()
        hw_mgr_mock = hardware_mock.return_value
        hw_mgr_mock.get_os_install_device.return_value = 'boot_device'
        hw_mgr_mock.get_image_manager.return_value = 'img_mgr'

        async_result = self.agent_extension.cache_image(
                image_info=image_info, force=True)
        async_result.join()
        write_mock.assert_called_once_with('img_mgr', image_info,
                                           'boot_device', force=True)
        self.assertEqual('SUCCEEDED', async_result.command_status)
        self.assertEqual(None, async_result.command_result)

    @mock.patch.object(standby.StandbyExtension, '_write_image')
    @mock.patch('ironic_python_agent.hardware.get_manager', autospec=True)
    def test_prepare_image(self, hardware_mock, write_mock):
        image_info = self._build_fake_image_info()
        hw_mgr_mock = hardware_mock.return_value
        hw_mgr_mock.get_os_install_device.return_value = 'boot_device'
        img_mgr_mock = hw_mgr_mock.get_image_manager.return_value

        async_result = self.agent_extension.prepare_image(
                image_info=image_info,
                configdrive='configdrive_data')
        async_result.join()
        write_mock.assert_called_once_with(img_mgr_mock, image_info,
                                           'boot_device')
        img_mgr_mock.write_configdrive.assert_called_once_with(
                'configdrive_data', 'boot_device')
        self.assertEqual('SUCCEEDED', async_result.command_status)
        self.assertEqual(None, async_result.command_result)

    @mock.patch.object(standby.StandbyExtension, '_write_image')
    @mock.patch('ironic_python_agent.hardware.get_manager', autospec=True)
    def test_prepare_image_no_configdrive(self, hardware_mock, write_mock):
        image_info = self._build_fake_image_info()
        hw_mgr_mock = hardware_mock.return_value
        hw_mgr_mock.get_os_install_device.return_value = 'boot_device'
        img_mgr_mock = hw_mgr_mock.get_image_manager.return_value

        async_result = self.agent_extension.prepare_image(
                image_info=image_info,
                configdrive=None)
        async_result.join()
        write_mock.assert_called_once_with(img_mgr_mock, image_info,
                                           'boot_device')
        self.assertFalse(img_mgr_mock.write_configdrive.called)
        self.assertEqual('SUCCEEDED', async_result.command_status)
        self.assertEqual(None, async_result.command_result)

    @mock.patch('ironic_python_agent.utils.execute', autospec=True)
    def test_run_image(self, execute_mock):
        script = standby._path_to_script('shell/reboot.sh')
        command = ['/bin/bash', script]
        execute_mock.return_value = ('', '')

        success_result = self.agent_extension.run_image()
        success_result.join()

        execute_mock.assert_called_once_with(*command, check_exit_code=[0])
        self.assertEqual('SUCCEEDED', success_result.command_status)

        execute_mock.reset_mock()
        execute_mock.return_value = ('', '')
        execute_mock.side_effect = processutils.ProcessExecutionError

        failed_result = self.agent_extension.run_image()
        failed_result.join()

        execute_mock.assert_called_once_with(*command, check_exit_code=[0])
        self.assertEqual('FAILED', failed_result.command_status)

    def test_path_to_script(self):
        script = standby._path_to_script('shell/reboot.sh')
        self.assertTrue(script.endswith('extensions/../shell/reboot.sh'))
