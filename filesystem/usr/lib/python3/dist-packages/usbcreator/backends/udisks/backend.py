import dbus
import logging
from dbus.mainloop.glib import DBusGMainLoop, threads_init
from gi.repository import Gio, GLib, UDisks
from usbcreator.backends.base import Backend
from usbcreator import misc

no_options = GLib.Variant('a{sv}', {})

loop_prefix = '/org/freedesktop/UDisks2/block_devices/loop'

not_interesting = (
    '/org/freedesktop/UDisks2/block_devices/dm_',
    '/org/freedesktop/UDisks2/block_devices/ram',    
    '/org/freedesktop/UDisks2/block_devices/zram',
    '/org/freedesktop/UDisks2/drives/', 
    )

import time

class UDisksBackend(Backend):
    def __init__(self, allow_system_internal=False, bus=None, show_all=False):
        Backend.__init__(self)
        self.mounted_source = ''
        self.formatting = []
        self.handles = []
        self.show_all = show_all
        self.allow_system_internal = allow_system_internal
        logging.debug('UDisks2Backend')
        DBusGMainLoop(set_as_default=True)
        threads_init()
        if bus:
            self.bus = bus
        else:
            self.bus = dbus.SystemBus()

        self.udisks = UDisks.Client.new_sync(None)

        self.helper = self.bus.get_object('com.ubuntu.USBCreator',
                                          '/com/ubuntu/USBCreator')
        self.helper = dbus.Interface(self.helper, 'com.ubuntu.USBCreator')

    # Adapted from udisk's test harness.
    # This is why the entire backend needs to be its own thread.
    def retry_mount(self, fs):
        '''Try to mount until it does not fail with "Busy".'''
        timeout = 10
        while timeout >= 0:
            try:
                return fs.call_mount_sync(no_options, None)
            except GLib.GError as e:
                if not 'UDisks2.Error.DeviceBusy' in e.message:
                    raise
                logging.debug('Busy.')
                time.sleep(0.3)
                timeout -= 1
        return ''

    # Device detection and processing functions.

    def detect_devices(self):
        '''Start looking for new devices to add.  Devices added will be sent to
        the fronted using frontend.device_added.  Devices will only be added as
        they arrive if a main loop is present.'''
        logging.debug('detect_devices')
        # TODO connect add/remove objects + changed interface signals
        self.manager = self.udisks.get_object_manager()
        self.handles += [self.manager.connect('object-added', lambda man, obj: self._udisks_obj_added(obj))]
        self.handles += [self.manager.connect('object-removed', lambda man, obj: self._device_removed(obj.get_object_path()))]
        self.handles += [self.manager.connect('interface-added', lambda man, obj, iface: self._device_changed(obj))]
        self.handles += [self.manager.connect('interface-removed', lambda man, obj, iface: self._device_changed(obj))]
        self.handles += [self.manager.connect('interface-proxy-properties-changed', lambda man, obj, iface, props, invalid: self._device_changed(obj))]
        for obj in self.manager.get_objects():
            self._udisks_obj_added(obj)

    def _udisks_obj_added(self, obj):
        path = obj.get_object_path()
        for boring in not_interesting:
            if path.startswith(boring):
                return

        block = obj.get_block()
        if not block:
            return
        
        drive_name = block.get_cached_property('Drive').get_string()
        if drive_name != '/':
            drive = self.udisks.get_object(drive_name).get_drive()
        else:
            drive = None
            
        if drive and drive.get_cached_property('Optical').get_boolean():
            self._udisks_cdrom_added(obj, block, drive, path)

        part = obj.get_partition()
        is_system = block.get_cached_property('HintSystem').get_boolean()
        is_loop = path.startswith(loop_prefix) and not block.get_cached_property('ReadOnly').get_boolean()
        if self.allow_system_internal or not is_system or is_loop:
            if part:
                self._udisks_partition_added(obj, block, drive, path)
            else:
                self._udisks_drive_added(obj, block, drive, path)
            
    def _udisks_cdrom_added(self, obj, block, drive, path):
        logging.debug('cd added: %s' % path)
        fs = obj.get_filesystem()
        if not fs:
            logging.debug('cd %s has no filesystem.' % path)
            return
        mount_points = fs.get_cached_property('MountPoints').get_bytestring_array()
        if len(mount_points) == 0:
            try:
                mount = fs.mount_sync(no_options, None)
            except GLib.GError as e:
                logging.exception('Could not mount the device: %s' % e.message)
        else:
            mount = mount_points[0]
        total, free = misc.fs_size(mount)
        self.sources[path] = {
            'device' : block.get_cached_property('Device').get_bytestring().decode('utf-8'),
            'size'   : total,
            'label'  : block.get_cached_property('IdLabel').get_string(),
            'type'   : misc.SOURCE_CD,
            'mount'  : mount,
        }
        if misc.callable(self.source_added_cb):
            self.source_added_cb(path)
        
    def _udisks_partition_added(self, obj, block, drive, path):
        logging.debug('partition added: %s' % path)
        fstype = block.get_cached_property('IdType').get_string()
        logging.debug('id-type: %s' % fstype)
        if fstype == 'vfat':
            status = misc.CAN_USE
        else:
            status = misc.NEED_FORMAT

        if drive:
            vendor = drive.get_cached_property('Vendor').get_string()
            model = drive.get_cached_property('Model').get_string()
            size = drive.get_cached_property('Size').get_uint64()            
        else:
            vendor = ''
            model = ''
            size = block.get_cached_property('Size').get_uint64()
            
        partition = obj.get_partition()
        parent = partition.get_cached_property('Table').get_string()
        fs = obj.get_filesystem()
        if fs:
            mount_points = fs.get_cached_property('MountPoints').get_bytestring_array()
            if (
                    fstype == 'vfat' and
                    len(mount_points) == 0 and
                    path not in self.formatting and
                    parent not in self.formatting):
                try:
                    mount = self.retry_mount(fs)
                except:
                    logging.exception('Could not mount the device: %s' % path)
                    return
            else:
                mount = mount_points and mount_points[0]
        else:
            mount = None

        if mount:
            total, free = misc.fs_size(mount)
        else:
            # FIXME evand 2009-09-11: This is going to have weird side effects.
            # If the device cannot be mounted, but is a vfat filesystem, that
            # is.  Is this really the right approach?
            total = size
            free = -1
            mount = ''
        logging.debug('mount: %s' % mount)
        if total > 1:
            self.targets[path] = {
                'vendor'     : vendor,
                'model'      : model,
                'label'      : block.get_cached_property('IdLabel').get_string(),
                'free'       : free,
                'device'     : block.get_cached_property('Device').get_bytestring().decode('utf-8'),
                'capacity'   : total,
                'status'     : status,
                'mountpoint' : mount,
                'persist'    : 0,
                'parent'     : misc.text_type(parent),
                'formatting' : False,
            }
            self._update_free(path)
            if self.show_all:
                if misc.callable(self.target_added_cb):
                    self.target_added_cb(device)
            else:
                if status != misc.NEED_FORMAT:
                    if parent in self.targets:
                        if misc.callable(self.target_removed_cb):
                            self.target_removed_cb(parent)
                    if misc.callable(self.target_added_cb):
                        self.target_added_cb(path)
        else:
            logging.debug('not adding device: 0 byte partition.')            
             
    def _udisks_drive_added(self, obj, block, drive, path):
        logging.debug('drive added: %s' % path)

        if drive:
            vendor = drive.get_cached_property('Vendor').get_string()
            model = drive.get_cached_property('Model').get_string()
            size = drive.get_cached_property('Size').get_uint64()            
        else:
            vendor = ''
            model = ''
            size = block.get_cached_property('Size').get_uint64()

        if size <= 0:
            logging.debug('not adding device: 0 byte disk.')
            return

        self.targets[path] = {
            'vendor': vendor,
            'model' : model,
            'label' : '',
            'free'  : -1,
            'device': block.get_cached_property('Device').get_bytestring().decode('utf-8'),
            'capacity' : size,
            'status' : misc.NEED_FORMAT,
            'mountpoint' : None,
            'persist' : 0,
            'parent' : None,
            'formatting' : False,
        }
        if misc.callable(self.target_added_cb):
            if self.show_all:
                self.target_added_cb(path)
            else:
                children = [x for x in self.targets
                            if self.targets[x]['parent'] == path and
                               self.targets[x]['status'] != misc.NEED_FORMAT]
                if not children:
                    self.target_added_cb(path)
            
    def _device_changed(self, obj):
        path = obj.get_object_path()
        logging.debug('device change %s' % path)
        # As this will happen in the same event, the frontend wont change
        # (though it needs to make sure the list is sorted, otherwise it will).
        self._device_removed(path)
        self._udisks_obj_added(obj)

    # Device manipulation functions.
    def _is_casper_cd(self, filename):
        cmd = ['isoinfo', '-J', '-i', filename, '-x', '/.disk/info']
        try:
            output = misc.popen(cmd, stderr=None)
            if output:
                return output
        except misc.USBCreatorProcessException:
            # TODO evand 2009-07-26: Error dialog.
            logging.error('Could not extract .disk/info.')
        return None

    def open(self, udi):
        mp = self.targets[udi]['mountpoint']
        if not mp:
            try:
                obj = self.udisks.get_object(udi)
                fs = obj.get_filesystem()
                if not fs:
                    return ''
                mp = fs.call_mount_sync(no_options, None)
            except GLib.GError:
                logging.exception('Could not mount the device:')
                return ''
        try:
            misc.popen(['mount', '-o', 'remount,rw', mp])
        except misc.USBCreatorProcessException:
            logging.exception('Could not mount the device:')
            return ''
        return mp

    def format_done(self, dev=None):
        if dev in self.targets:
            p = self.targets[dev]['parent']
            if p and p in self.targets:
                dev = p
            self.targets[dev]['formatting'] = False
            self.formatting.remove(dev)

    def format_ended(self, dev=None):
        self.format_done(dev)
        obj = self.udisks.get_object(dev)
        self._device_changed(obj)
        self.format_ended_cb()

    def format_failed(self, message, dev=None):
        self.format_done(dev)
        self.format_failed_cb(message)

    def format(self, device):
        try:
            p = self.targets[device]['parent']
            if p and p in self.targets:
                self.formatting.append(p)
                self.targets[p]['formatting'] = True
            else:
                self.formatting.append(device)
                self.targets[device]['formatting'] = True
            self.helper.Format(device, self.allow_system_internal,
                    # There must be a better way...
                    reply_handler=lambda: self.format_ended(device),
                    error_handler=lambda x: self.format_failed(x, device))
        except GLib.GError as e:
            # Could not talk to usb-creator-helper or devkit.
            logging.exception('Could not format the device:')

    def install(self, source, target, persist, allow_system_internal=False):
        # TODO evand 2009-07-31: Lock source and target.
        logging.debug('install source: %s' % source)
        logging.debug('install target: %s' % target)
        logging.debug('install persistence: %d' % persist)

        # There's no going back now...
        for handle in self.handles:
            self.manager.disconnect(handle)

        stype = self.sources[source]['type']
        if stype == misc.SOURCE_CD:
            source = self.sources[source]['mount']
        elif stype == misc.SOURCE_ISO:
            isofile = self.sources[source]['device']
            source = self.helper.MountISO(isofile)
            self.mounted_source = source

        dev = self.targets[target]['device']
        if stype == misc.SOURCE_IMG:
            target_path = None
            self.helper.Unmount(target)
        else:
            obj = self.udisks.get_object(target)
            fs = obj.get_filesystem()
            mount_points = fs.get_cached_property('MountPoints').get_bytestring_array()
            if len(mount_points) == 0:
                target_path = fs.mount_sync(no_options, None)
            else:
                target_path = mount_points[0]
            self.helper.RemountRW(dev)
        Backend.install(self, source, target_path, persist, device=dev,
                        allow_system_internal=allow_system_internal)

    def cancel_install(self):
        Backend.cancel_install(self)
        self.unmount()

    def unmount(self):
        try:
            if self.mounted_source:
                self.helper.UnmountFile(self.mounted_source)
        except:
            # TODO let the user know via the frontend.
            logging.exception('Could not unmount the source ISO.')

    def shutdown(self):
        try:
            self.helper.Shutdown()
        except GLib.GError as e:
            logging.exception('Could not shut down the dbus service.')
