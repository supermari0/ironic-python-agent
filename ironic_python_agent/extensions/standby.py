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

import os
import six
import time

from ironic_python_agent import errors
from ironic_python_agent.extensions import base
from ironic_python_agent import hardware
from ironic_python_agent.openstack.common import log
from ironic_python_agent.openstack.common import processutils
from ironic_python_agent import utils

LOG = log.getLogger(__name__)


def _path_to_script(script):
    cwd = os.path.dirname(os.path.realpath(__file__))
    return os.path.join(cwd, '..', script)


def _validate_image_info(ext, image_info=None, **kwargs):
    image_info = image_info or {}

    for field in ['id', 'urls', 'checksum']:
        if field not in image_info:
            msg = 'Image is missing \'{0}\' field.'.format(field)
            raise errors.InvalidCommandParamsError(msg)

    if type(image_info['urls']) != list or not image_info['urls']:
        raise errors.InvalidCommandParamsError(
            'Image \'urls\' must be a list with at least one element.')

    if (not isinstance(image_info['checksum'], six.string_types)
            or not image_info['checksum']):
        raise errors.InvalidCommandParamsError(
            'Image \'checksum\' must be a non-empty string.')


class StandbyExtension(base.BaseAgentExtension):
    def __init__(self):
        super(StandbyExtension, self).__init__()

        self.cached_image_id = None

    def _write_image(self, img_mgr, image_info, device, force=False):
        if self.cached_image_id != image_info['id'] or force:
            LOG.info('Writing image %(id)s to device %(device)s',
                     {'id': image_info['id'],
                      'device': device})
            starttime = time.time()
            img_mgr.write_os_image(image_info, device)
            totaltime = time.time() - starttime
            self.cached_image_id = image_info['id']
            LOG.info('Image %(id)s written to device %(device)s in '
                     '%(secs)s second(s)',
                     {'id': image_info['id'],
                      'device': device,
                      'secs': totaltime})
        else:
            LOG.info('Image %(id)s already written to device %(device)s',
                     {'id': image_info['id'],
                      'device': device})

    @base.async_command('cache_image', _validate_image_info)
    def cache_image(self, image_info=None, force=False):
        hw_mgr = hardware.get_manager()
        device = hw_mgr.get_os_install_device()
        img_mgr = hw_mgr.get_image_manager(image_info)
        self._write_image(img_mgr, image_info, device, force=force)

    @base.async_command('prepare_image', _validate_image_info)
    def prepare_image(self, image_info=None, configdrive=None):
        hw_mgr = hardware.get_manager()
        device = hw_mgr.get_os_install_device()
        img_mgr = hw_mgr.get_image_manager(image_info)
        self._write_image(img_mgr, image_info, device)

        if configdrive is None:
            LOG.info('No configdrive to write to device %(device)s',
                     {'device': device})
        else:
            LOG.info('Writing configdrive to device %(device)s',
                     {'device': device})
            starttime = time.time()
            img_mgr.write_configdrive(configdrive, device)
            totaltime = time.time() - starttime
            LOG.info('Wrote configdrive to device %(device)s in '
                     '%(secs)s second(s)',
                     {'device': device,
                      'secs': totaltime})

    @base.async_command('run_image')
    def run_image(self):
        script = _path_to_script('shell/reboot.sh')
        LOG.info('Rebooting system')
        command = ['/bin/bash', script]
        # this should never return if successful
        try:
            stdout, stderr = utils.execute(*command, check_exit_code=[0])
        except processutils.ProcessExecutionError as e:
            raise errors.SystemRebootError(e.exit_code, e.stdout, e.stderr)
