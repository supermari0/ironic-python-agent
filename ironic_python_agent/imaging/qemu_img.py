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

from ironic_python_agent import errors
from ironic_python_agent.imaging import base
from ironic_python_agent.openstack.common import log
from ironic_python_agent.openstack.common import processutils
from ironic_python_agent import utils

LOG = log.getLogger(__name__)


class QemuImgImageManager(base.BaseImageManager):
    def write_os_image(self, image_info, device):
        """Download image and write it to a device."""
        with self._download_image(image_info) as location:
            script = self._path_to_script('shell/qemu_img_write_image.sh')
            command = ['/bin/bash', script, location, device]
            LOG.info('Writing image with command: %(cmd)s',
                     {'cmd': ' '.join(command)})
            try:
                stdout, stderr = utils.execute(*command, check_exit_code=[0])
            except processutils.ProcessExecutionError as e:
                raise errors.ImageWriteError(device, e.exit_code, e.stdout,
                                             e.stderr)
