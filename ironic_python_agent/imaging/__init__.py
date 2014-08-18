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

from ironic_python_agent.imaging import qemu_img

_DISK_FORMAT_MAPPING = {'qcow2': qemu_img.QemuImgImageManager}


def get_image_manager(disk_format, container_format):
    return _DISK_FORMAT_MAPPING.get(disk_format,
                                    qemu_img.QemuImgImageManager)()
