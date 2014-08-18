# Copyright 2013-2014 Rackspace, Inc.
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

import contextlib

import mock
from oslotest import base as test_base

from ironic_python_agent import errors
from ironic_python_agent.imaging import base
from ironic_python_agent.imaging import qemu_img
from ironic_python_agent.openstack.common import processutils


class TestQemuImgImageManager(test_base.BaseTestCase):
    def setUp(self):
        super(TestQemuImgImageManager, self).setUp()
        self.qemuimg_img_mgr = qemu_img.QemuImgImageManager()

    @mock.patch('ironic_python_agent.utils.execute')
    @mock.patch.object(base.BaseImageManager, '_path_to_script')
    @mock.patch.object(base.BaseImageManager, '_download_image')
    def test_write_os_image(self, dl_mock, path_mock, exec_mock):
        image_info = 'fake image info'
        device = 'device'
        path_mock.return_value = 'fake path'
        exec_mock.return_value = (None, None)

        @contextlib.contextmanager
        def _unpack_side_effect(_data):
            yield 'fake location'

        dl_mock.side_effect = _unpack_side_effect

        exp_command = ['/bin/bash', 'fake path',
                       'fake location', device]

        self.qemuimg_img_mgr.write_os_image(image_info, device)

        dl_mock.assert_called_once_with(image_info)
        path_mock.assert_called_once_with(
                'shell/qemu_img_write_image.sh')
        exec_mock.assert_called_once_with(*exp_command,
                                          check_exit_code=[0])

    @mock.patch('ironic_python_agent.utils.execute')
    @mock.patch.object(base.BaseImageManager, '_path_to_script')
    @mock.patch.object(base.BaseImageManager, '_download_image')
    def test_write_os_image_exec_fail(self, dl_mock, path_mock, exec_mock):
        image_info = 'fake image info'
        device = 'device'
        path_mock.return_value = 'fake path'
        exec_mock.side_effect = processutils.ProcessExecutionError()

        @contextlib.contextmanager
        def _unpack_side_effect(_data):
            yield 'fake location'

        dl_mock.side_effect = _unpack_side_effect

        exp_command = ['/bin/bash', 'fake path',
                       'fake location', device]

        self.assertRaises(
                errors.ImageWriteError,
                self.qemuimg_img_mgr.write_os_image,
                image_info,
                device)

        dl_mock.assert_called_once_with(image_info)
        path_mock.assert_called_once_with(
                'shell/qemu_img_write_image.sh')
        exec_mock.assert_called_once_with(*exp_command,
                                          check_exit_code=[0])
