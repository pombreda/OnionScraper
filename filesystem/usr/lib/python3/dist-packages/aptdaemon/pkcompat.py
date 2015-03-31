# !/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Provides a limited compatibility layer to PackageKit

Copyright (C) 2007 Ali Sabil <ali.sabil@gmail.com>
Copyright (C) 2007 Tom Parker <palfrey@tevp.net>
Copyright (C) 2008-2011 Sebastian Heinlein <glatzor@ubuntu.com>

Licensed under the GNU General Public License Version 2

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.
"""

__author__ = "Sebastian Heinlein <devel@glatzor.de>"

import datetime
import glob
import gzip
import locale
import logging
import os
import platform
import re
import subprocess
import tempfile
import time
import uuid

from defer import inline_callbacks, return_value
from defer.utils import dbus_deferred_method
import dbus
from gi.repository import GObject, GLib
from gi.repository import PackageKitGlib as pk

# for optional plugin support
try:
    import pkg_resources
except ImportError:
    pkg_resources = None

from . import policykit1
from . import core
from .core import APTDAEMON_TRANSACTION_DBUS_INTERFACE
from . import enums as aptd_enums
from .errors import TransactionFailed
from . import errors
from .progress import DaemonAcquireProgress
from . import worker
from . import networking
from .pkutils import (bitfield_summarize, bitfield_add, bitfield_remove,
                      bitfield_contains)
from .utils import split_package_id


pklog = logging.getLogger("AptDaemon.PackageKit")

# Check if update-manager-core is installed to get aware of the
# latest distro releases
try:
    from UpdateManager.Core.MetaRelease import MetaReleaseCore
except ImportError:
    META_RELEASE_SUPPORT = False
else:
    META_RELEASE_SUPPORT = True

PACKAGEKIT_DBUS_INTERFACE = "org.freedesktop.PackageKit"
PACKAGEKIT_DBUS_SERVICE = "org.freedesktop.PackageKit"
PACKAGEKIT_DBUS_PATH = "/org/freedesktop/PackageKit"

PACKAGEKIT_TRANS_DBUS_INTERFACE = "org.freedesktop.PackageKit.Transaction"
PACKAGEKIT_TRANS_DBUS_SERVICE = "org.freedesktop.PackageKit.Transaction"

MAP_EXIT_ENUM = {
    aptd_enums.EXIT_SUCCESS: pk.ExitEnum.SUCCESS,
    aptd_enums.EXIT_CANCELLED: pk.ExitEnum.CANCELLED,
    aptd_enums.EXIT_FAILED: pk.ExitEnum.FAILED,
    aptd_enums.EXIT_FAILED: pk.ExitEnum.FAILED,
    aptd_enums.EXIT_PREVIOUS_FAILED: pk.ExitEnum.FAILED}

MAP_STATUS_ENUM = {
    aptd_enums.STATUS_AUTHENTICATING: pk.StatusEnum.WAITING_FOR_AUTH,
    aptd_enums.STATUS_SETTING_UP: pk.StatusEnum.SETUP,
    aptd_enums.STATUS_QUERY: pk.StatusEnum.QUERY,
    aptd_enums.STATUS_WAITING: pk.StatusEnum.WAIT,
    aptd_enums.STATUS_RUNNING: pk.StatusEnum.RUNNING,
    aptd_enums.STATUS_CANCELLING: pk.StatusEnum.CANCEL,
    aptd_enums.STATUS_CLEANING_UP: pk.StatusEnum.CLEANUP,
    aptd_enums.STATUS_COMMITTING: pk.StatusEnum.COMMIT,
    aptd_enums.STATUS_DOWNLOADING: pk.StatusEnum.DOWNLOAD,
    aptd_enums.STATUS_DOWNLOADING_REPO: pk.StatusEnum.DOWNLOAD_REPOSITORY,
    aptd_enums.STATUS_FINISHED: pk.StatusEnum.FINISHED,
    aptd_enums.STATUS_LOADING_CACHE: pk.StatusEnum.LOADING_CACHE,
    aptd_enums.STATUS_RESOLVING_DEP: pk.StatusEnum.DEP_RESOLVE,
    aptd_enums.STATUS_RUNNING: pk.StatusEnum.RUNNING,
    aptd_enums.STATUS_WAITING_LOCK: pk.StatusEnum.WAITING_FOR_LOCK,
    aptd_enums.STATUS_WAITING_MEDIUM: pk.StatusEnum.UNKNOWN,
    aptd_enums.STATUS_WAITING_CONFIG_FILE_PROMPT: pk.StatusEnum.UNKNOWN}

MAP_ERROR_ENUM = {
    aptd_enums.ERROR_CACHE_BROKEN: pk.ErrorEnum.NO_CACHE,
    aptd_enums.ERROR_DEP_RESOLUTION_FAILED: (
        pk.ErrorEnum.DEP_RESOLUTION_FAILED),
    aptd_enums.ERROR_INCOMPLETE_INSTALL: pk.ErrorEnum.NO_CACHE,
    aptd_enums.ERROR_INVALID_PACKAGE_FILE: (
        pk.ErrorEnum.PACKAGE_CORRUPT),
    aptd_enums.ERROR_KEY_NOT_INSTALLED: pk.ErrorEnum.GPG_FAILURE,
    aptd_enums.ERROR_KEY_NOT_REMOVED: pk.ErrorEnum.GPG_FAILURE,
    aptd_enums.ERROR_NOT_REMOVE_ESSENTIAL_PACKAGE: (
        pk.ErrorEnum.PACKAGE_FAILED_TO_REMOVE),
    aptd_enums.ERROR_NO_CACHE: pk.ErrorEnum.NO_CACHE,
    aptd_enums.ERROR_NO_LOCK: pk.ErrorEnum.CANNOT_GET_LOCK,
    aptd_enums.ERROR_NO_PACKAGE: pk.ErrorEnum.PACKAGE_NOT_FOUND,
    aptd_enums.ERROR_PACKAGE_ALREADY_INSTALLED: (
        pk.ErrorEnum.PACKAGE_ALREADY_INSTALLED),
    aptd_enums.ERROR_PACKAGE_DOWNLOAD_FAILED: (
        pk.ErrorEnum.PACKAGE_DOWNLOAD_FAILED),
    aptd_enums.ERROR_PACKAGE_MANAGER_FAILED: (
        pk.ErrorEnum.TRANSACTION_ERROR),
    aptd_enums.ERROR_PACKAGE_NOT_INSTALLED: (
        pk.ErrorEnum.PACKAGE_NOT_INSTALLED),
    aptd_enums.ERROR_PACKAGE_UNAUTHENTICATED: (
        pk.ErrorEnum.BAD_GPG_SIGNATURE),
    aptd_enums.ERROR_PACKAGE_UPTODATE: (
        pk.ErrorEnum.NO_PACKAGES_TO_UPDATE),
    aptd_enums.ERROR_REPO_DOWNLOAD_FAILED: (
        pk.ErrorEnum.REPO_NOT_AVAILABLE),
    aptd_enums.ERROR_UNREADABLE_PACKAGE_FILE: (
        pk.ErrorEnum.INVALID_PACKAGE_FILE),
    aptd_enums.ERROR_SYSTEM_ALREADY_UPTODATE: (
        pk.ErrorEnum.NO_PACKAGES_TO_UPDATE),
    aptd_enums.ERROR_NOT_AUTHORIZED: pk.ErrorEnum.NOT_AUTHORIZED,
    aptd_enums.ERROR_AUTH_FAILED: pk.ErrorEnum.NOT_AUTHORIZED}

MAP_PACKAGE_ENUM = {
    aptd_enums.PKG_CONFIGURING: pk.InfoEnum.INSTALLING,
    aptd_enums.PKG_DISAPPEARING: pk.InfoEnum.UNKNOWN,
    aptd_enums.PKG_INSTALLED: pk.InfoEnum.FINISHED,
    aptd_enums.PKG_INSTALLING: pk.InfoEnum.INSTALLING,
    aptd_enums.PKG_PREPARING_INSTALL: pk.InfoEnum.PREPARING,
    aptd_enums.PKG_PREPARING_PURGE: pk.InfoEnum.PREPARING,
    aptd_enums.PKG_PREPARING_REMOVE: pk.InfoEnum.PREPARING,
    aptd_enums.PKG_PURGED: pk.InfoEnum.FINISHED,
    aptd_enums.PKG_PURGING: pk.InfoEnum.REMOVING,
    aptd_enums.PKG_REMOVED: pk.InfoEnum.FINISHED,
    aptd_enums.PKG_REMOVING: pk.InfoEnum.REMOVING,
    aptd_enums.PKG_RUNNING_TRIGGER: pk.InfoEnum.CLEANUP,
    aptd_enums.PKG_UNKNOWN: pk.InfoEnum.UNKNOWN,
    aptd_enums.PKG_UNPACKING: pk.InfoEnum.DECOMPRESSING,
    aptd_enums.PKG_UPGRADING: pk.InfoEnum.UPDATING}

MAP_POLICY = {
    "org.freedesktop.packagekit.cancel-foreign": (
        policykit1.PK_ACTION_CANCEL_FOREIGN),
    "org.freedesktop.packagekit.package-install": (
        policykit1.PK_ACTION_INSTALL_OR_REMOVE_PACKAGES),
    "org.freedesktop.packagekit.package-install-untrusted": (
        policykit1.PK_ACTION_INSTALL_OR_REMOVE_PACKAGES),
    "org.freedesktop.packagekit.system-trust-signing-key": (
        policykit1.PK_ACTION_CHANGE_REPOSITORY),
    "org.freedesktop.packagekit.package-eula-accept": (
        policykit1.PK_ACTION_INSTALL_OR_REMOVE_PACKAGES),
    "org.freedesktop.packagekit.package-remove": (
        policykit1.PK_ACTION_INSTALL_OR_REMOVE_PACKAGES),
    "org.freedesktop.packagekit.system-update": (
        policykit1.PK_ACTION_UPGRADE_PACKAGES),
    "org.freedesktop.packagekit.system-sources-configure": (
        policykit1.PK_ACTION_CHANGE_REPOSITORY),
    "org.freedesktop.packagekit.system-sources-refresh": (
        policykit1.PK_ACTION_UPDATE_CACHE),
    "org.freedesktop.packagekit.system-network-proxy-configure": (
        policykit1.PK_ACTION_SET_PROXY),
    "org.freedesktop.packagekit.device-rebind": (
        policykit1.PK_ACTION_INSTALL_OR_REMOVE_PACKAGES),
    "org.freedesktop.packagekit.upgrade-system": (
        policykit1.PK_ACTION_UPGRADE_PACKAGES),
    "org.freedesktop.packagekit.repair-system": (
        policykit1.PK_ACTION_INSTALL_OR_REMOVE_PACKAGES),
    "org.freedesktop.packagekit.trigger-offline-update": (
        policykit1.PK_ACTION_UPGRADE_PACKAGES),
    "org.freedesktop.packagekit.clear-offline-update": (
        policykit1.PK_ACTION_UPGRADE_PACKAGES)}


class PackageKit(core.DBusObject):

    """Provides a limited set of the PackageKit system D-Bus API."""

    def __init__(self, queue, connect=True, bus=None):
        """Initialize a new PackageKit compatibility layer.

        Keyword arguments:
        connect -- if the daemon should connect to the D-Bus (default is True)
        bus -- the D-Bus to connect to (defaults to the system bus)
        """
        pklog.info("Initializing PackageKit compat layer")
        bus_name = None
        bus_path = None
        if connect is True:
            if bus is None:
                bus = dbus.SystemBus()
            self.bus = bus
            bus_path = PACKAGEKIT_DBUS_PATH
            bus_name = dbus.service.BusName(PACKAGEKIT_DBUS_SERVICE, self.bus)
        core.DBusObject.__init__(self, bus_name, bus_path)
        self._updates_changed_timeout_id = None
        self._updates_changed = False
        self.queue = queue
        self.queue.worker.connect("transaction-done",
                                  self._on_transaction_done)
        self.queue.connect("queue-changed", self._on_queue_changed)
        self._distro_id = None
        self.netmon = networking.get_network_monitor()
        self.netmon.connect("network-state-changed",
                            self._on_network_state_changed)
        self._get_network_state()

    @inline_callbacks
    def _get_network_state(self):
        """Helper to defer the network state checking."""
        yield self.netmon.get_network_state()

    # SIGNALS

    # pylint: disable-msg=C0103,C0322
    @dbus.service.signal(dbus_interface=PACKAGEKIT_DBUS_INTERFACE,
                         signature="")
    def RestartSchedule(self):
        """A system restart has been sceduled."""
        pass

    # pylint: disable-msg=C0103,C0322
    @dbus.service.signal(dbus_interface=PACKAGEKIT_DBUS_INTERFACE,
                         signature="as")
    def TransactionListChanged(self, transactions):
        """The transaction list has changed, because either a transaction
        has finished or a new transaction created.

        :param transactions: A list of transaction ID's.
        :type transactions: as
        """
        pklog.debug("Emitting TransactionListChanged signal: %s", transactions)

    # pylint: disable-msg=C0103,C0322
    @dbus.service.signal(dbus_interface=PACKAGEKIT_DBUS_INTERFACE,
                         signature="")
    def UpdatesChanged(self):
        """This signal is emitted when the number of updates has changed."""
        pklog.debug("Emitting UpdatesChanged signal")

    # pylint: disable-msg=C0103,C0322
    @dbus.service.signal(dbus_interface=PACKAGEKIT_DBUS_INTERFACE,
                         signature="")
    def RepoListChanged(self):
        """This signal is emitted when the repository list has changed."""
        pass

    # pylint: disable-msg=C0103,C0322
    @dbus.service.signal(dbus_interface=PACKAGEKIT_DBUS_INTERFACE,
                         signature="")
    def Changed(self):
        """This signal is emitted when a property on the interface changes."""
        pklog.debug("Emitting PackageKit Changed()")

    # METHODS

    # pylint: disable-msg=C0103,C0322
    @dbus_deferred_method(PACKAGEKIT_DBUS_INTERFACE,
                          in_signature="s", out_signature="u",
                          sender_keyword="sender")
    def CanAuthorize(self, action_id, sender):
        """Allows a client to find out if it would be allowed to authorize
        an action.

        :param action_id: The action ID, e.g.
                org.freedesktop.packagekit.system-network-proxy-configure
        :returns: The result, either yes, no or interactive.
        """
        pklog.info("CanAuthorize() was called: %s", str(action_id))
        return self._can_authorize(action_id, sender)

    @inline_callbacks
    def _can_authorize(self, action_id, sender):
        try:
            action_id_aptd = MAP_POLICY[action_id]
        except KeyError:
            return_value(pk.AuthorizeEnum.UNKNOWN)
        try:
            policykit1.check_authorization_by_name(
                self, action_id, flags=policykit1.CHECK_AUTH_NONE)
        except policykit1.NotAuthorizedError:
            return_value(pk.AuthorizeEnum.NO)
        except policykit1.AuthorizationFailed:
            # check_authorization_* behaves a little bit different if the
            # flags are set to NONE instead of INTERACTIVE
            return_value(pk.AuthorizeEnum.INTERACTIVE)
        except:
            return_value(pk.AuthorizeEnum.UNKNOWN)
        return_value(pk.AuthorizeEnum.YES)

    # pylint: disable-msg=C0103,C0322
    @dbus.service.method(PACKAGEKIT_DBUS_INTERFACE,
                         in_signature="s", out_signature="")
    def StateHasChanged(self, reason):
        """This method suggests to PackageKit that the package backend state
        may have changed. This allows plugins to the native package manager
        to suggest that PackageKit drops it's caches.

        :param reason:
            The reason of the state change. Valid reasons are resume or
            posttrans. Resume is given a lower priority than posttrans.
        """
        pklog.info("StateHasChanged() was called: %s", str(reason))
        self._updates_changed = True
        if reason == "cache-update":
            self._check_updates_changed(timeout=30)
        elif reason == "resume":
            self._check_updates_changed(timeout=180)

    # pylint: disable-msg=C0103,C0322
    @dbus_deferred_method(PACKAGEKIT_DBUS_INTERFACE,
                          in_signature="", out_signature="o",
                          sender_keyword="sender")
    def CreateTransaction(self, sender):
        """Gets a new transaction ID from the daemon.

        :returns: The tid, e.g. 45_dafeca_checkpoint32
        """
        pklog.info("CreateTransaction() was called")
        return self._create_transaction(sender)

    @inline_callbacks
    def _create_transaction(self, sender):
        pid, uid, cmdline = yield policykit1.get_proc_info_from_dbus_name(
            sender, self.bus)
        pktrans = PackageKitTransaction(pid, uid, cmdline, self.queue, sender)
        return_value(pktrans.tid)

    # pylint: disable-msg=C0103,C0322
    @dbus.service.method(PACKAGEKIT_DBUS_INTERFACE,
                         in_signature="", out_signature="s")
    def GetDaemonState(self):
        """Return the state of the currently running transactions."""
        pklog.info("GetDaemonState() was called")
        # FIXME: Add some useful data here
        return "All is fine!"

    # pylint: disable-msg=C0103,C0322
    @dbus.service.method(PACKAGEKIT_DBUS_INTERFACE,
                         in_signature="", out_signature="ao")
    def GetTransactionList(self):
        """Gets the transaction list of any transactions that are in
        progress.

        :returns: A list of transaction ID's
        """
        pklog.info("GetTransactionList() was called")
        return self._get_transaction_list()

    # HELPERS

    def _get_properties(self, iface):
        """Helper to get the properties of a D-Bus interface."""
        if iface == PACKAGEKIT_DBUS_INTERFACE:
            return {
                # Claim that we are a current version
                "VersionMajor": dbus.UInt32(0),
                "VersionMinor": dbus.UInt32(8),
                "VersionMicro": dbus.UInt32(9),
                "BackendName": dbus.String("aptdaemon"),
                "BackendDescription": dbus.String("Compatibility layer"),
                "BackendAuthor": dbus.String(__author__),
                "Groups": dbus.UInt64(self.queue.worker.groups),
                "Provides": dbus.UInt64(self.queue.worker.provides),
                "Filters": dbus.UInt64(self.queue.worker.filters),
                "Roles": dbus.UInt64(self.queue.worker.roles),
                "MimeTypes": dbus.Array(self.queue.worker.mime_types,
                                        signature="s"),
                "Locked": dbus.Boolean(False),
                "NetworkState": dbus.UInt32(self.netmon.state),
                "DistroId": dbus.String(self._get_distro_id())}
        else:
            return {}

    def _get_distro_id(self):
        """Return information about the distibution."""
        if self._distro_id is None:
            distro, version, _codename = platform.dist()
            self._distro_id = "%s;%s;%s" % (distro or "unknown",
                                            version or "unknown",
                                            NATIVE_ARCH)
        return self._distro_id

    def _on_network_state_changed(self, mon, state):
        self.Changed()
        self.PropertiesChanged(PACKAGEKIT_DBUS_INTERFACE,
                               {"NetworkState": dbus.UInt32(state)}, [])

    def _on_queue_changed(self, queue):
        self.TransactionListChanged(self._get_transaction_list())
        self._check_updates_changed()

    def _get_transaction_list(self):
        pk_transactions = []
        for trans in self.queue.items:
            # We currently only emit PackageKit transaction
            # FIXME: Should we use MergedTransaction for all transactions and
            #       ROLE_UNKOWN for aptdaemon only transactions?
            try:
                pk_transactions.append(trans.pktrans.tid)
            except AttributeError:
                pass
        try:
            pk_transactions.append(self.queue.worker.trans.pktrans.tid)
        except AttributeError:
            pass
        return pk_transactions

    def _on_transaction_done(self, worker, trans):
        # If a cache modifing transaction is completed schedule an
        # UpdatesChanged signal
        if trans.role in (aptd_enums.ROLE_INSTALL_FILE,
                          aptd_enums.ROLE_INSTALL_PACKAGES,
                          aptd_enums.ROLE_REMOVE_PACKAGES,
                          aptd_enums.ROLE_UPGRADE_PACKAGES,
                          aptd_enums.ROLE_COMMIT_PACKAGES,
                          aptd_enums.ROLE_UPGRADE_SYSTEM,
                          aptd_enums.ROLE_FIX_BROKEN_DEPENDS):
            self._updates_changed = True
            self._check_updates_changed()
        elif trans.role == aptd_enums.ROLE_UPDATE_CACHE:
            self._updates_changed = True
            self._check_updates_changed(timeout=30)

    def _check_updates_changed(self, timeout=60):
        """After the queue was processed schedule a delayed UpdatesChanged
        signal if required.
        """
        if not self.queue.items and self._updates_changed:
            if self._updates_changed_timeout_id:
                # If we already have a scheduled UpdatesChanged signal
                # delay it even further
                pklog.debug("UpdatesChanged signal re-scheduled")
                GLib.source_remove(self._updates_changed_timeout_id)
            else:
                pklog.debug("UpdatesChanged signal scheduled")
            self._updates_changed_timeout_id = \
                GLib.timeout_add_seconds(timeout,
                                         self._delayed_updates_changed)

    def _delayed_updates_changed(self):
        """Emit the UpdatesChanged signal and clear the timeout."""
        self.UpdatesChanged()
        self._updates_changed_timeout_id = None
        self._updates_changed = False
        return False


class MergedTransaction(core.Transaction):

    """Overlay of an Aptdaemon transaction which also provides the
    PackageKit object and its interfaces.
    """

    def __init__(self, pktrans, role, queue, connect=True,
                 bus=None, packages=None, kwargs=None):
        core.Transaction.__init__(self, pktrans.tid[1:], role, queue,
                                  pktrans.pid, pktrans.uid,
                                  pktrans.cmdline, pktrans.sender,
                                  connect, bus, packages, kwargs)
        self.pktrans = pktrans
        self.run_time = 0

    @inline_callbacks
    def _run(self, sender):
        """Run the transaction and convert exceptions to PackageKit ones."""
        try:
            yield core.Transaction._run(self, sender)
        except (TransactionFailed, errors.NotAuthorizedError,
                errors.AuthorizationFailed):
            # It is sufficient for PackageKit if the exit state and error
            # code of the transaction are set. So silently drop the execp
            if self.error:
                pass
        except Exception as error:
            raise error

    @inline_callbacks
    def _check_auth(self):
        """Override the auth method to allow simulates without any
        authorization.
        """
        if bitfield_contains(self.pktrans.flags,
                             pk.TransactionFlagEnum.SIMULATE):
            raise StopIteration
        else:
            yield core.Transaction._check_auth(self)

    @inline_callbacks
    def _check_simulated(self):
        """Skip simulate calls for simulated transactions."""
        if bitfield_contains(self.pktrans.flags,
                             pk.TransactionFlagEnum.SIMULATE):
            raise StopIteration
        else:
            yield core.Transaction._check_simulated(self)

    def _set_status(self, enum):
        core.Transaction._set_status(self, enum)
        self.pktrans.status = get_pk_status_enum(enum)

    status = property(core.Transaction._get_status, _set_status)

    def _set_progress(self, percent):
        core.Transaction._set_progress(self, percent)
        self.pktrans.percentage = self._progress

    progress = property(core.Transaction._get_progress, _set_progress)

    def _set_progress_details(self, details):
        core.Transaction._set_progress_details(self, details)
        self.pktrans.download_size_remaing = int(details[3]) - int(details[2])
        self.pktrans.speed = int(details[4])
        self.pktrans.remaining_time = int(details[5])
        self.pktrans.elapsed_time = int(time.time() - self.pktrans.start_time)

    progress_details = property(core.Transaction._get_progress_details,
                                _set_progress_details)

    def _set_progress_package(self, progress):
        core.Transaction._set_progress_package(self, progress)
        pkg_name, enum = progress
        # Ignore dpkg triggers
        if enum == aptd_enums.PKG_RUNNING_TRIGGER or pkg_name == "dpkg-exec":
            return
        try:
            id = self.pktrans.pkg_id_cache[pkg_name]
        except KeyError:
            id = get_pk_package_id(pkg_name)
        self.emit_package(get_pk_package_enum(enum), id, "")

    progress_package = property(core.Transaction._get_progress_package,
                                _set_progress_package)

    def _set_progress_download(self, progress_download):
        core.Transaction._set_progress_download(self, progress_download)
        prog_enum = progress_download[1]
        prog_name = progress_download[2]
        total_size = progress_download[3]
        partial_size = progress_download[4]

        try:
            id = self.pktrans.pkg_id_cache[prog_name]
        except KeyError:
            return
        self.pktrans.Package(pk.InfoEnum.DOWNLOADING, id, "")
        if prog_enum == aptd_enums.DOWNLOAD_IDLE:
            percentage = 0
        elif prog_enum == aptd_enums.DOWNLOAD_FETCHING and total_size > 0:
            percentage = partial_size * 100 / total_size
        elif prog_enum == aptd_enums.DOWNLOAD_DONE:
            percentage = 100
        else:
            # In the case of an error
            percentage = 0
        self.pktrans.ItemProgress(id, pk.InfoEnum.DOWNLOADING, percentage)

    progress_download = property(core.Transaction._get_progress_download,
                                 _set_progress_download)

    def _set_exit(self, enum):
        core.Transaction._set_exit(self, enum)
        self.pktrans.exit = get_pk_exit_enum(enum)

    exit = property(core.Transaction._get_exit, _set_exit)

    def _set_error(self, excep):
        core.Transaction._set_error(self, excep)
        self.pktrans.ErrorCode(get_pk_error_enum(excep.code),
                               self._error_property[1])

    error = property(core.Transaction._get_error, _set_error)

    def _remove_from_connection_no_raise(self):
        core.Transaction._remove_from_connection_no_raise(self)
        self.pktrans.Destroy()
        try:
            self.pktrans.remove_from_connection()
        except LookupError as error:
            pklog.debug("remove_from_connection() raised LookupError: %s",
                        error)
        finally:
            self.pktrans.trans = None
            self.pktrans = None
        return False

    def emit_details(self, package_id, license, group, detail, url, size):
        self.pktrans.Details(package_id, license, group, detail, url, size)

    def emit_files(self, id, file_list):
        self.pktrans.Files(id, file_list)

    def emit_package(self, info, id, summary):
        if id.startswith("dpkg-exec;"):
            # PackageKit would show a non existing package
            pklog.debug("Don't emit Package() signal for the dpkg trigger")
            return
        self.pktrans.Package(info, id, summary)
        self.pktrans.last_package = id

    def emit_update_detail(self, package_id, updates, obsoletes, vendor_urls,
                           bugzilla_urls, cve_urls, restart, update_text,
                           changelog, state, issued, updated):
        self.pktrans.UpdateDetail(package_id, updates, obsoletes, vendor_urls,
                                  bugzilla_urls, cve_urls, restart,
                                  update_text, changelog, state, issued,
                                  updated)


class PackageKitTransaction(core.DBusObject):

    """Provides a PackageKit transaction object."""

    def __init__(self, pid, uid, cmdline, queue, sender,
                 connect=True, bus=None):
        pklog.info("Initializing PackageKit transaction")
        bus_name = None
        bus_path = None
        self.tid = "/%s" % uuid.uuid4().hex
        if connect is True:
            if bus is None:
                bus = dbus.SystemBus()
            self.bus = bus
            bus_path = self.tid
            bus_name = dbus.service.BusName(PACKAGEKIT_DBUS_SERVICE, bus)
        core.DBusObject.__init__(self, bus_name, bus_path)
        self.queue = queue
        self.hints = {}
        self.start_time = time.time()
        self._elapsed_time = dbus.UInt32(0)
        self._remaining_time = dbus.UInt32(0)
        self._download_size_remaining = dbus.UInt64(0)
        self._speed = dbus.UInt32(0)
        self._caller_active = True
        self._allow_cancel = False
        self._percentage = dbus.UInt32(0)
        self._status = pk.StatusEnum.SETUP
        self._last_package = ""
        self.uid = dbus.UInt32(uid)
        self.pid = pid
        self.cmdline = cmdline
        self.role = pk.RoleEnum.UNKNOWN
        self.sender = sender
        self.trans = None
        self.flags = pk.TransactionFlagEnum.NONE
        self.pkg_id_cache = {}

    @property
    def allow_cancel(self):
        return self._allow_cancel

    @allow_cancel.setter
    def allow_cancel(self, value):
        self._allow_cancel = dbus.Boolean(value)
        self.PropertiesChanged(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                               {"AllowCancel": self._allow_cancel}, [])
        self.Changed()

    @property
    def last_package(self):
        return self._last_package

    @last_package.setter
    def last_package(self, value):
        self._last_package = dbus.String(value)
        self.PropertiesChanged(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                               {"LastPackage": self._last_package}, [])
        self.Changed()

    @property
    def caller_active(self):
        return self._caller_active

    @caller_active.setter
    def caller_active(self, value):
        self._caller_active = dbus.Boolean(value)
        self.PropertiesChanged(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                               {"CallerActive": self._caller_active}, [])
        self.Changed()

    @property
    def percentage(self):
        return self._percentage

    @percentage.setter
    def percentage(self, progress):
        self._percentage = dbus.UInt32(progress)
        self.PropertiesChanged(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                               {"Percentage": self._percentage}, [])
        self.Changed()

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, enum):
        self._status = dbus.UInt32(enum)
        self.PropertiesChanged(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                               {"Status": self._status}, [])
        self.Changed()

    @property
    def elapsed_time(self):
        return self._elapsed_time

    @elapsed_time.setter
    def elapsed_time(self, ela):
        self._elpased_time = dbus.UInt32(ela)
        self.PropertiesChanged(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                               {"ElapsedTime": self._elapsed_time}, [])
        self.Changed()

    @property
    def remaining_time(self):
        return self._remaining_time

    @remaining_time.setter
    def remaining_time(self, value):
        self._remaining_time = dbus.UInt32(value)
        self.PropertiesChanged(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                               {"RemainingTime": self._remaining_time}, [])
        self.Changed()

    @property
    def download_size_remaining(self):
        return self._download_size_remaining

    @download_size_remaining.setter
    def download_size_remaining(self, value):
        self._download_size_remaining = dbus.UInt64(value)
        self.PropertiesChanged(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                               {"DownloadSizeRemaining":
                                self._download_size_remaining}, [])
        self.Changed()

    @property
    def speed(self):
        return self._speed

    @speed.setter
    def speed(self, speed):
        self._speed = dbus.UInt32(speed)
        self.PropertiesChanged(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                               {"Speed": self._speed}, [])
        self.Changed()

    @property
    def exit(self):
        return self._exit

    @exit.setter
    def exit(self, enum):
        self._exit = enum
        self.run_time = int((time.time() - self.start_time) * 1000)
        # The time could go backwards ...
        if self.run_time < 0:
            self.run_time = 0
        if enum == pk.ExitEnum.CANCELLED:
            self.ErrorCode(pk.ErrorEnum.TRANSACTION_CANCELLED, "")
        self.status = pk.StatusEnum.FINISHED
        self.Finished(enum, self.run_time)

    # SIGNALS

    # pylint: disable-msg=C0103,C0322
    @dbus.service.signal(dbus_interface=PACKAGEKIT_TRANS_DBUS_INTERFACE,
                         signature="osbuusus")
    def Transaction(self, object_path, timespec, succeeded, role, duration,
                    data, uid, cmdline):
        """This signal is sent when more details are required about a
        specific transaction.

        :param object_path: The transaction ID of the old transaction.
        :param timespec: The timespec of the old transaction in ISO8601 format.
        :param succeeded: If the transaction succeeded.
        :param role: The role enumerated type.
        :param duration: The duration of the transaction in milliseconds.
        :param data: Any data associated
        :param uid: The user ID of the user that scheduled the action.
        :param cmdline: The command line of the tool that scheduled the action,
            e.g. /usr/bin/gpk-application.
        """
        pklog.debug("Emitting Transaction signal: %s, %s, %s, %s, %s, %s, "
                    "%s, %s", object_path, timespec, succeeded,
                    pk.role_enum_to_string(role), duration, data, uid,
                    cmdline)

    # pylint: disable-msg=C0103,C0322
    @dbus.service.signal(dbus_interface=PACKAGEKIT_TRANS_DBUS_INTERFACE,
                         signature="us")
    def ErrorCode(self, code, details):
        """This signal is used to report errors back to the session program.
        Errors should only be send on fatal abort.

        :param code: Enumerated type, e.g. no-network.
        :param details: Long description or error, e.g. "failed to connect"

        :type code: u
        :type details: s
        """
        pklog.debug("Emitting ErrorCode signal: %s, %s",
                    pk.error_enum_to_string(code), details)

    # pylint: disable-msg=C0103,C0322
    @dbus.service.signal(dbus_interface=PACKAGEKIT_TRANS_DBUS_INTERFACE,
                         signature="")
    def Changed(self):
        """This signal is emitted when a property on the interface changes."""
        pklog.debug("Emitting Changed signal")

    # pylint: disable-msg=C0103,C0322
    @dbus.service.signal(dbus_interface=PACKAGEKIT_TRANS_DBUS_INTERFACE,
                         signature="")
    def Destroy(self):
        """This signal is sent when the transaction has been destroyed
        and is no longer available for use."""
        pklog.debug("Emitting Destroy signal")

    # pylint: disable-msg=C0103,C0322
    @dbus.service.signal(dbus_interface=PACKAGEKIT_TRANS_DBUS_INTERFACE,
                         signature="uu")
    def Finished(self, exit_enum, runtime):
        """This signal is used to signal that the transaction has finished.
        :param exit: The PkExitEnum describing the exit status of the
            transaction.
        :param runtime: The amount of time in milliseconds that the
            transaction ran for.

        :type exit: s
        :type runtime: u
        """
        pklog.debug("Emitting Finished signal: %s, %s",
                    pk.exit_enum_to_string(exit_enum), runtime)
        pass

    # pylint: disable-msg=C0103,C0322
    @dbus.service.signal(dbus_interface=PACKAGEKIT_TRANS_DBUS_INTERFACE,
                         signature="ssusst")
    def Details(self, package_id, license, group, detail, url, size):
        """This signal allows the backend to convey more details about the
        package.

        :param package_id: The package ID

        :param license:
            The license string, e.g. GPLv2+ or BSD and (MPLv1.1 or GPLv2+).
            Moredetails about the correct way to format licensing strings can
            be found on the Fedora packaging wiki.
        :param group:
            The enumerated package group description
        :param detail:
            The multi-line package description. If formatting is required,
            then markdown syntax should be used, e.g. This is **critically**
            important
        :param url:
            The upstream project homepage
        :param size:
            The size of the package in bytes. This should be the size of the
            entire package file, not the size of the files installed on the
            system. If the package is not installed, and already downloaded
            and present in the package manager cache, then this value should
            be set to zero.
        """
        pklog.debug("Emitting Details signal for %s", package_id)

    # pylint: disable-msg=C0103,C0322
    @dbus.service.signal(dbus_interface=PACKAGEKIT_TRANS_DBUS_INTERFACE,
                         signature="us")
    def Message(self, kind, details):
        """This signal is sent when the backend wants to send a message to
        the session.

        The message will be shown after the transaction has been completed.
        """
        pklog.debug("Emitting Message signal: %s, %s", kind, details)

    # pylint: disable-msg=C0103,C0322
    @dbus.service.signal(dbus_interface=PACKAGEKIT_TRANS_DBUS_INTERFACE,
                         signature="sas")
    def Files(self, package_id, file_list):
        """This signal is used to push file lists from the backend to the
        session.

        :param package_id:
            The Package ID that called the method.
        :param file_list:
            The file list
        """
        pklog.debug("Emitting Files signal: %s, %s", package_id, file_list)

    # pylint: disable-msg=C0103,C0322
    @dbus.service.signal(dbus_interface=PACKAGEKIT_TRANS_DBUS_INTERFACE,
                         signature="suu")
    def ItemProgress(self, package_id, status, percentage):
        """This signal allows the backend to send information about
        package or repository progress when using Simultanous mode.

        :param package_id: The package ID
        :param status:
            The status enumerated value that is being completed
        :param percentage:
            The percentage of this action is completed
        """
        pklog.debug("Emitting ItemProgress signal for %s: %s, %s",
                    package_id, pk.info_enum_to_string(status), percentage)

    # pylint: disable-msg=C0103,C0322
    @dbus.service.signal(dbus_interface=PACKAGEKIT_TRANS_DBUS_INTERFACE,
                         signature="sasasasasasussuss")
    def UpdateDetail(self, package_id, updates, obsoletes, vendor_urls,
                     bugzilla_urls, cve_urls, restart, update_text, changelog,
                     state, issued, updated):
        """This signal is sent when more details are required about a
        specific update.

        :param package_id: The package ID
        :param updates:
            A list of package_id's that are to be updated.
        :param obsoletes:
            A list of package_id's that are to be obsoleted.
        :param vendor_urls:
            A URL with more details on the update, e.g. a page with more
            information on the update. The format of this command should
            be http://www.foo.org/page.html?4567;Update to SELinux
        :param bugzilla_urls:
            A bugzilla URL with more details on the update. If no URL is
            available then this field should be left empty.
        :param cve_urls:
            A CVE URL with more details on the security advisory.
        :param restart:
            A valid restart type, e.g. system.
        :param update_text:
            The update text describing the update. If formatting is required,
            then markdown syntax should be used, e.g. This is **critically**
            important.
        :param changelog:
            The ChangeLog text describing the changes since the last version.
        :param state:
            The state of the update, e.g. stable or testing.
        :param issued:
            The ISO8601 encoded date that the update was issued.
        :param updated:
            The ISO8601 encoded date that the update was updated.
        """
        pklog.debug("Emitting UpdateDetail signal for %s", package_id)

    # pylint: disable-msg=C0103,C0322
    @dbus.service.signal(dbus_interface=PACKAGEKIT_TRANS_DBUS_INTERFACE,
                         signature="uss")
    def Package(self, info, package_id, summary):
        """This signal allows the backend to communicate packages to the
        session.

        If updating, as packages are updated then emit them to the screen.
        This allows a summary to be presented after the transaction.
        When returning results from a search always return installed
        before available for the same package name.

        :param info: A valid info enumerated type
        :param package_id: This identifier is of the form
            name;version;arch;data in a single string and is meant to
            represent a single package unique across all local and remote
            data stores. For a remote, not-installed package the data
            field should be set as the repository identifier or repository
            name. The data field for an installed package must be prefixed
            with installed as this is used to identify which packages are
            installable or installed in the client tools. As a special
            extension, if the package manager is able to track which
            repository a package was originally installed from, then the data
            field can be set to installed:REPO-NAME which allows the frontend
            client to advise the user of the package origin. The data field
            for a non-installed local package must be local as this signifies
            a repository name is not available and that package resides
            locally on the client system rather than in any specific
            repository.
        :param summary: The one line package summary, e.g. Clipart for
            OpenOffice
        """
        pklog.debug("Emitting Package signal: %s, %s, %s'",
                    pk.info_enum_to_string(info), package_id, summary[:10])

    # pylint: disable-msg=C0103,C0322
    @dbus.service.signal(dbus_interface=PACKAGEKIT_TRANS_DBUS_INTERFACE,
                         signature="sss")
    def DistroUpgrade(self, distro_type, name, summary):
        """This signal allows the backend to communicate distribution upgrades
        to the session.
        :param type: A valid upgrade string enumerated type, e.g. stable
            or unstable
        :param name: The short name of the distribution, e.g. Fedora Core
            10 RC1
        :param summary: The multi-line description of the release
        """
        pklog.debug("Emitting DistroUpgrade signal: %s, %s, %s",
                    pk.distro_upgrade_enum_to_string(distro_type),
                    name, summary)

    # pylint: disable-msg=C0103,C0322
    @dbus.service.signal(dbus_interface=PACKAGEKIT_TRANS_DBUS_INTERFACE,
                         signature="us")
    def RequireRestart(self, restart_type, package_id):
        """This signal is sent when the session client should notify the user
        that a restart is required to get all changes into effect.

        :param package_id:
            The Package ID of the package tiggering the restart
        :param file_list:
            One of system, application or session
        """
        pklog.debug("Emitting RequireRestart signal: %s, %s",
                    pk.restart_enum_to_string(restart_type), package_id)

    # METHODS

    # pylint: disable-msg=C0103,C0322
    @dbus.service.method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                         in_signature="as", out_signature="")
    def SetHints(self, hints):
        """This method allows the calling session to set transaction hints
        for the package manager which can change as the transaction runs.

        This method can be sent before the transaction has been run or
        whilst it is running. There is no limit to the number of times
        this method can be sent, although some backends may only use the
        values that were set before the transaction was started.

        Each parameter value is optional.

        :param hints: The values as an array of strings, for example
            ['locale=en_GB.utf8','interactive=false','cache-age=3600']
        """
        pklog.info("SetHints() was called: %s", get_string_from_array(hints))
        for hint in hints:
            key, value = hint.split("=", 1)
            if key not in ["locale", "idle", "background", "interactive",
                           "cache-age", "frontend-socket"]:
                raise Exception("Invalid option %s" % key)
            self.hints[key] = value

    # pylint: disable-msg=C0103,C0322
    @dbus_deferred_method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                          in_signature="", out_signature="",
                          sender_keyword="sender")
    def Cancel(self, sender):
        """This method cancels a transaction that is already running."""
        if self.trans:
            return self.trans._cancel(sender)

    # pylint: disable-msg=C0103,C0322
    @dbus_deferred_method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                          in_signature="tasbb", out_signature="",
                          sender_keyword="sender")
    def RemovePackages(self, flags, package_ids, allow_deps, autoremove,
                       sender):
        """This method removes packages from the local system.

        This method typically emits Progress, Status and Error and Package.

        Package enumerated types should be downloading, updating,
        installing or removing.

        :param flags: If the transaction should be simulated or prepared
        :param package_ids: An array of package IDs.
        :param allow_deps:
            Either true or false. If true allow other packages to be removed
            with the package, but false should cause the script to abort if
            other packages are dependant on the package.
        :param autoremove:
            Either true or false. This option is only really interesting on
            embedded devices with a limited amount of flash storage. It
            suggests to the packagekit backend that dependencies installed at
            the same time as the package should also be removed if they are not
            required by anything else. For instance, if you install OpenOffice,
            it might download libneon as a dependency. When auto_remove is set
            to true, and you remove OpenOffice then libneon will also get
            removed automatically.
        """
        pklog.info("RemovePackages() was called: %s, %s",
                   get_string_from_flags(flags),
                   get_string_from_array(package_ids))
        return self._remove_packages(flags, package_ids, allow_deps,
                                     autoremove, sender)

    @inline_callbacks
    def _remove_packages(self, flags, package_ids, allow_deps, autoremove,
                         sender):
        self.role = pk.RoleEnum.REMOVE_PACKAGES
        self.flags = flags
        self.trans = self._get_merged_trans(aptd_enums.ROLE_REMOVE_PACKAGES,
                                            pkg_ids=package_ids,
                                            pkg_type=aptd_enums.PKGS_REMOVE)
        yield self.trans._set_property(APTDAEMON_TRANSACTION_DBUS_INTERFACE,
                                       "RemoveObsoletedDepends", autoremove,
                                       sender)
        # FIXME: Implement allow_deps
        yield self.trans._run(sender)

    # pylint: disable-msg=C0103,C0322
    @dbus_deferred_method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                          in_signature="tas", out_signature="",
                          sender_keyword="sender")
    def UpdatePackages(self, flags, package_ids, sender):
        """This method updates existing packages on the local system.

        The installer should always update extra packages automatically
        to fulfil dependencies.

        This should allow an application to find out what package owns a
        file on the system.

        This method typically emits Progress, Status and Error and Package.

        :param flags:
            If the transaction is only allowed to install trusted packages.
            Unsigned packages should not be installed if the flags
            contains ONLY_TRUSED.
            If this method is can only install trusted packages, and
            the packages are unsigned, then the backend will send a
            ErrorCode(missing-gpg-signature). On recieving this error, the
            client may choose to retry with ONLY_TRUSTED set after
            gaining further authentication.
        : param package_ids: An array of package IDs.
        """
        pklog.info("UpdatePackages() was called: %s, %s",
                   get_string_from_flags(flags),
                   get_string_from_array(package_ids))
        return self._update_packages(flags, package_ids, sender)

    @inline_callbacks
    def _update_packages(self, flags, package_ids, sender):
        self.role = pk.RoleEnum.UPDATE_PACKAGES
        self.flags = flags
        self.trans = self._get_merged_trans(aptd_enums.ROLE_UPGRADE_PACKAGES,
                                            pkg_ids=package_ids,
                                            pkg_type=aptd_enums.PKGS_UPGRADE)
        yield self.trans._set_property(
            APTDAEMON_TRANSACTION_DBUS_INTERFACE,
            "AllowUnauthenticated",
            not bitfield_contains(flags,
                                  pk.TransactionFlagEnum.ONLY_TRUSTED),
            sender)
        yield self.trans._run(sender)

    # pylint: disable-msg=C0103,C0322
    @dbus_deferred_method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                          in_signature="uas", out_signature="",
                          sender_keyword="sender")
    def InstallPackages(self, flags, package_ids, sender):
        """This method installs new packages on the local system.

        The installer should always install extra packages automatically
        as the use could call GetDepends prior to the install if a
        confirmation is required in the UI.

        This method typically emits Progress, Status and Error and Package.

        Package enumerated types should be downloading, updating,
        installing or removing.

        :param flags:
            If the transaction is only allowed to install trusted packages.
            Unsigned packages should not be installed if the flags
            contains ONLY_TRUSED.
            If this method is can only install trusted packages, and
            the packages are unsigned, then the backend will send a
            ErrorCode(missing-gpg-signature). On recieving this error, the
            client may choose to retry with ONLY_TRUSTED set after
            gaining further authentication.
        : param package_ids: An array of package IDs.
        """
        pklog.info("InstallPackages() was called: %s, %s",
                   get_string_from_flags(flags),
                   get_string_from_array(package_ids))
        return self._install_packages(flags, package_ids, sender)

    @inline_callbacks
    def _install_packages(self, flags, package_ids, sender):
        self.role = pk.RoleEnum.INSTALL_PACKAGES
        self.flags = flags
        self.trans = self._get_merged_trans(aptd_enums.ROLE_INSTALL_PACKAGES,
                                            pkg_ids=package_ids,
                                            pkg_type=aptd_enums.PKGS_INSTALL)
        yield self.trans._set_property(
            APTDAEMON_TRANSACTION_DBUS_INTERFACE,
            "AllowUnauthenticated",
            not bitfield_contains(flags,
                                  pk.TransactionFlagEnum.ONLY_TRUSTED),
            sender)
        yield self.trans._run(sender)

    # pylint: disable-msg=C0103,C0322
    @dbus.service.method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                         in_signature="su", out_signature="",
                         sender_keyword="sender")
    def UpgradeSystem(self, distro_id, upgrade_kind, sender):
        """This method updates existing packages on the local system.

        The installer should always update extra packages automatically
        to fulfil dependencies.

        This should allow an application to find out what package owns a
        file on the system.

        This method typically emits Progress, Status and Error and Package.

        :param distro_id: The distribution id to upgrade to, e.g. saucy
        :param upgrade_kind:
            The type of upgrade e.g. minimal, default or complete.
            Minimal upgrades will download the smallest amount of data
            before launching a installer.
            The default is to download enough data to launch a full graphical
            installer, but a complete upgrade will be required if there is no
            internet access during install time.
        """
        pklog.info("UpgradeSystem() was called")
        GLib.idle_add(self._fail_not_implemented)

    # pylint: disable-msg=C0103,C0322
    @dbus_deferred_method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                          in_signature="t", out_signature="",
                          sender_keyword="sender")
    def RepairSystem(self, flags, sender):
        """This method recovers the package managment system from e.g.
        unsatisified dependencies of installed packages.

        :param flags:
            If the transaction is only allowed to install trusted packages.
            Unsigned packages should not be installed if the flags
            contains ONLY_TRUSED.
            If this method is can only install trusted packages, and
            the packages are unsigned, then the backend will send a
            ErrorCode(missing-gpg-signature). On recieving this error, the
            client may choose to retry with ONLY_TRUSTED set after
            gaining further authentication.
        """
        pklog.info("RepairSystem() was called")
        return self._repair_system(flags, sender)

    @inline_callbacks
    def _repair_system(self, flags, sender):
        self.role = pk.RoleEnum.REPAIR_SYSTEM
        self.flags = flags
        self.trans = self._get_merged_trans(aptd_enums.ROLE_FIX_BROKEN_DEPENDS)
        yield self.trans._set_property(
            APTDAEMON_TRANSACTION_DBUS_INTERFACE,
            "AllowUnauthenticated",
            not bitfield_contains(flags,
                                  pk.TransactionFlagEnum.ONLY_TRUSTED),
            sender)
        yield self.trans._run(sender)

    # pylint: disable-msg=C0103,C0322
    @dbus_deferred_method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                          in_signature="b", out_signature="",
                          sender_keyword="sender")
    def RefreshCache(self, force, sender):
        """This method should fetch updated meta-data for all enabled
        repositories.

        When fetching each software source, ensure to emit RepoDetail for
        the current source to give the user interface some extra details.
        Be sure to have the "enabled" field set to true, otherwise you
        wouldn't be fetching that source.

        This method typically emits Progress, Error and RepoDetail.

        :param force: If the caches should be cleaned and reloaded even if
            there is valid, up to date data.
        """
        pklog.info("RefreshCache() was called")
        self.role = pk.RoleEnum.REFRESH_CACHE
        return self._refresh_cache(force, sender)

    @inline_callbacks
    def _refresh_cache(self, force, sender):
        self.trans = self._get_merged_trans(aptd_enums.ROLE_UPDATE_CACHE,
                                            kwargs={"sources_list": None})
        yield self.trans._run(sender)

    @dbus_deferred_method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                          in_signature="as", out_signature="",
                          sender_keyword="sender")
    def GetUpdateDetail(self, package_ids, sender):
        """This method returns details about a specific update.

        This method typically emits UpdateDetail and Error

        :param package_ids: An array of package IDs.
        """
        pklog.info("GetUpdateDetail() was called")
        self.role = pk.RoleEnum.GET_UPDATE_DETAIL
        kwargs = {"package_ids": package_ids}
        return self._run_query(kwargs, sender)

    @dbus_deferred_method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                          in_signature="t", out_signature="",
                          sender_keyword="sender")
    def GetUpdates(self, filter, sender):
        """This method should return a list of packages that are installed
        and are upgradable. It should only return the newest update for
        each installed package.

        This method typically emits Progress, Error and Package.

        :param filter: A correct filter, e.g. none or installed;~devel
        """
        pklog.info("GetUpdates() was called")
        self.role = pk.RoleEnum.GET_UPDATES
        kwargs = {"filters": filter}
        return self._run_query(kwargs, sender)

    @dbus.service.method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                         in_signature="", out_signature="",
                         sender_keyword="sender")
    def GetDistroUpgrades(self, sender):
        """This method should return a list of distribution upgrades that are
        available. It should not return updates, only major upgrades.

        This method typically emits DistroUpgrade, Error
        """
        pklog.info("GetDistroUpgrades() was called")
        self.role = pk.RoleEnum.GET_DISTRO_UPGRADES
        self.status = pk.StatusEnum.RUNNING
        GLib.idle_add(defer_idle, self._get_distro_upgrades)

    def _get_distro_upgrades(self):
        # FIXME: Should go into the worker after the threading branch is merged
        #       It allows to run a nested loop until the download is finished
        self.allow_cancel = False
        self.percentage = 101
        self.status = pk.StatusEnum.DOWNLOAD_UPDATEINFO

        if META_RELEASE_SUPPORT is False:
            self.ErrorCode(pk.ErrorEnum.INTERNAL_ERROR,
                           "Please make sure that update-manager-core is"
                           "correctly installed.")
            self.exit = pk.ExitEnum.FAILED
            return

        # FIXME Evil to start the download during init
        meta_release = GMetaRelease()
        meta_release.connect("download-done",
                             self._on_distro_upgrade_download_done)

    def _on_distro_upgrade_download_done(self, meta_release):
        # FIXME: Add support for description
        if meta_release.new_dist is not None:
            self.DistroUpgrade("stable",
                               "%s %s" % (meta_release.new_dist.name,
                                          meta_release.new_dist.version),
                               "The latest stable release")
        self.exit = pk.ExitEnum.SUCCESS

    @dbus_deferred_method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                          in_signature="tas", out_signature="",
                          sender_keyword="sender")
    def Resolve(self, filter, packages, sender):
        """This method turns a single package name into a package_id suitable
        for the other methods.

        If the package is a fully formed package_id, then this should be
        treated as an exact package match. This is useful to find the summary
        or installed status of a package_id returned from other methods.

        This method typically emits Error and Package.

        Package enumerated types should be available or installed.

        :param filter: A correct filter, e.g. none or installed;~devel
        :param packages:
            An array of package names, e.g. scribus-clipart. The package
            names are case sensitive, so for instance: Resolve('Packagekit')
            would not match PackageKit. As a special case, if Resolve() is
            called with a name prefixed with @ then this should be treated as
            a category, for example: @web-development. In this instance, a
            meta-package should be emitted, for example:
            web-development;;;meta with the correct installed status and
            summary for the category.
        """
        pklog.info("Resolve() was called: %s", get_string_from_array(packages))
        self.role = pk.RoleEnum.RESOLVE
        kwargs = {"filters": filter, "packages": packages}
        return self._run_query(kwargs, sender)

    @dbus_deferred_method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                          in_signature="t", out_signature="",
                          sender_keyword="sender")
    def GetPackages(self, filter, sender):
        """This method returns all the packages without a search term.

        This method typically emits Progress, Error and Package.

        Package enumerated types should be available or installed.

        :param filter: A correct filter, e.g. none or installed;~devel
        """
        pklog.info("GetPackages() was called")
        self.role = pk.RoleEnum.GET_PACKAGES
        kwargs = {"filters": filter}
        return self._run_query(kwargs, sender)

    @dbus_deferred_method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                          in_signature="as", out_signature="",
                          sender_keyword="sender")
    def GetDetails(self, package_ids, sender):
        """This method should return all the details about a specific
        package_id.

        This method typically emits Progress, Status and Error and Details.

        :param package_ids: An array of package IDs.
        """
        pklog.info("GetDetails() was called")
        self.role = pk.RoleEnum.GET_DETAILS
        kwargs = {"package_ids": package_ids}
        return self._run_query(kwargs, sender)

    @dbus_deferred_method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                          in_signature="as", out_signature="",
                          sender_keyword="sender")
    def GetFiles(self, package_ids, sender):
        """This method should return the file list of the package_id.

        This method typically emits Progress, Status and Error and Files.

        :param package_ids: An array of package IDs.
        """
        pklog.info("GetFiles() was called")
        self.role = pk.RoleEnum.GET_FILES
        kwargs = {"package_ids": package_ids}
        return self._run_query(kwargs, sender)

    @dbus_deferred_method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                          in_signature="tas", out_signature="",
                          sender_keyword="sender")
    def SearchFiles(self, filter, values, sender):
        """This method searches for files on the local system and files in
        available packages.

        This should search for files. This should allow an application to
        find out what package owns a file on the system.

        This method typically emits Progress, Error and Package.

        Package enumerated types should be available or installed.

        :param filter: A correct filter, e.g. none or installed;~devel
        :param values:
            A filename or fully qualified path and filename on the system.
            If the search term begins with a / it will be assumed the entire
            path has been given and only packages that contain this exact
            path and filename will be returned. If the search term does not
            start with / then it should be treated as a single filename,
            which can be in any directory. The search is case sensitive,
            and should not be escaped or surrounded in quotes.
        """
        pklog.info("SearchFiles() was called")
        self.role = pk.RoleEnum.SEARCH_FILE
        kwargs = {"filters": filter,
                  "values": values}
        return self._run_query(kwargs, sender)

    @dbus_deferred_method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                          in_signature="tas", out_signature="",
                          sender_keyword="sender")
    def SearchDetails(self, filter, values, sender):
        """This method allows deeper searching than SearchName().

        Do not refresh the package cache. This should be fast. This is very
        similar to search-name. This should search as much data as possible,
        including, if possible repo names, package summaries, descriptions,
        licenses and URLs.

        Try to emit installed before available packages first, as it allows
        the client program to perform the GUI filtering and matching whilst
        the daemon is running the transaction.

        If the backend includes installed and available versions of the same
        package when searching then the available version will have to be
        filtered in the backend.

        This method typically emits Progress, Error and Package.

        Package enumerated types should be available or installed.

        :param filter: A correct filter, e.g. none or installed;~devel
        :param values:
            A single word search term with no wildcard chars. The search term
            can contain many words separated by spaces. In this case, the
            search operator is AND. For example, search of gnome power should
            returns gnome-power-manager but not gnomesword or powertop.
            The search should not be treated as case sensitive.
        """
        pklog.info("SearchDetails() was called")
        self.role = pk.RoleEnum.SEARCH_DETAILS
        kwargs = {"filters": filter,
                  "values": values}
        return self._run_query(kwargs, sender)

    @dbus_deferred_method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                          in_signature="tas", out_signature="",
                          sender_keyword="sender")
    def SearchGroups(self, filter, values, sender):
        """This method returns packages from a given group enumerated type.

        Do not refresh the package cache. This should be fast.

        Try to emit installed before available packages first, as it
        allows the client program to perform the GUI filtering and matching
        whilst the daemon is running the transaction.

        If the backend includes installed and available versions of the same
        package when searching then the available version will have to be
        filtered in the backend.

        This method typically emits Progress, Error and Package.

        Package enumerated types should be available or installed.

        :param filter: A correct filter, e.g. none or installed;~devel
        :param values:
            An enumerated group type, or unknown. The search cannot contain
            spaces. The following recommendations are made below: If the values
            strings are prefixed with category: then the request is treated
            as a 'category search', for example: category:web-development.
            repo: then the request is treated as a 'repository search', for
            example: repo:fedora-debuginfo. In this instance all packages that
            were either installed from, or can be installed from the
            fedora-debuginfo source would be returned.
        """
        pklog.info("SearchGroups() was called")
        self.role = pk.RoleEnum.SEARCH_GROUP
        kwargs = {"filters": filter,
                  "values": values}
        return self._run_query(kwargs, sender)

    @dbus_deferred_method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                          in_signature="tas", out_signature="",
                          sender_keyword="sender")
    def SearchNames(self, filter, values, sender):
        """This method searches the package database by package name.

        Try to emit installed before available packages first, as it
        allows the client program to perform the GUI filtering and matching
        whilst the daemon is running the transaction.

        If the backend includes installed and available versions of the same
        package when searching then the available version will have to be
        filtered in the backend.

        The search methods should return all results in all repositories.
        This may mean that multiple versions of package are returned. If this
        is not what is wanted by the client program, then the newest filter
        should be used.

        This method typically emits Progress, Error and Package.

        Package enumerated types should be available or installed.

        :param filter: A correct filter, e.g. none or installed;~devel
        :param values:
            A single word search term with no wildcard chars. The search term
            can contain many words separated by spaces. In this case, the
            search operator is AND. For example, search of gnome power should
            returns gnome-power-manager but not gnomesword or powertop.
            The search should not be treated as case sensitive.
        """
        pklog.info("SearchNames() was called")
        self.role = pk.RoleEnum.SEARCH_NAME
        kwargs = {"filters": filter,
                  "values": values}
        return self._run_query(kwargs, sender)

    @dbus.service.method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                         in_signature="s", out_signature="",
                         sender_keyword="sender")
    def AcceptEula(self, eula_id, sender):
        """This method allows the user to accept a end user licence agreement.

        :param eula_id: A valid EULA ID
        """
        self.role = pk.RoleEnum.ACCEPT_EULA
        GLib.idle_add(self._fail_not_implemented)

    @dbus_deferred_method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                          in_signature="bas", out_signature="",
                          sender_keyword="sender")
    def DownloadPackages(self, store_in_cache, package_ids, sender):
        """This method downloads packages into a temporary directory.

        This method should emit one Files signal for each package that
        is downloaded, with the file list set as the name of the complete
        downloaded file and directory, so for example:

        DownloadPackages('hal;0.1.2;i386;fedora',
        'hal-info;2009-09-07;no-arch;updates') should send two signals,
        e.g. Files('hal;0.1.2;i386;fedora', '/tmp/hal-0.1.2.i386.rpm')
        and Files('hal-info;2009-09-07;no-arch;updates',
        '/tmp/hal-info-2009-09-07.noarch.rpm').

        :param store_in_cache:
            If the downloaded files should be stored in the system package
            cache rather than copied into a newly created directory. See the
            developer docs for more details on how this is supposed to work.
        :param package_ids: An array of package IDs.
        """
        pklog.info("DownloadPackages() was called: %s",
                   get_string_from_array(package_ids))
        self.role = pk.RoleEnum.DOWNLOAD_PACKAGES
        kwargs = {"store_in_cache": store_in_cache,
                  "package_ids": package_ids}
        return self._run_query(kwargs, sender)

    @dbus.service.method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                         in_signature="u", out_signature="",
                         sender_keyword="sender")
    def GetOldTransactions(self, number, sender):
        """This method allows a client to view details for old transactions.

        :param number:
            The number of past transactions, or 0 for all known transactions.
        """
        pklog.info("GetOldTransactions() was called: %s", str(number))
        self.role = pk.RoleEnum.GET_OLD_TRANSACTIONS
        GLib.idle_add(self._fail_not_implemented)

    @dbus.service.method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                         in_signature="t", out_signature="",
                         sender_keyword="sender")
    def GetRepoList(self, filter, sender):
        """This method returns the list of repositories used in the system.

        This method should emit RepoDetail.

        :param filter: A correct filter, e.g. none or installed;~devel
        """
        pklog.info("GetRepoList() was called")
        self.role = pk.RoleEnum.GET_REPO_LIST
        GLib.idle_add(self._fail_not_implemented)

    @dbus_deferred_method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                          in_signature="tas", out_signature="",
                          sender_keyword="sender")
    def InstallFiles(self, flags, full_paths, sender):
        """This method installs local package files onto the local system.

        The installer should always install extra dependant packages
        automatically.

        This method typically emits Progress, Status and Error and Package.

        Package enumerated types should be downloading, updating, installing
        or removing.

        :param flags:
            If the transaction is only allowed to install trusted packages.
            Unsigned packages should not be installed if the flags
            contains ONLY_TRUSED.
            If this method is can only install trusted packages, and
            the packages are unsigned, then the backend will send a
            ErrorCode(missing-gpg-signature). On recieving this error, the
            client may choose to retry with ONLY_TRUSTED set after
            gaining further authentication.
        :param full_paths: An array of full path and filenames to packages.
        """
        pklog.info("InstallFiles() was called: %s, %s",
                   get_string_from_flags(flags),
                   get_string_from_array(full_paths))
        return self._install_files(flags, full_paths, sender)

    @inline_callbacks
    def _install_files(self, flags, full_paths, sender):
        self.role = pk.RoleEnum.INSTALL_FILES
        self.flags = flags
        # Python-APT only supports installing one file
        if len(full_paths) != 1:
            self.ErrorCode(pk.ErrorEnum.NOT_SUPPORTED,
                           "Only one package can be "
                           "installed at the same time.")
            self.exit = pk.ExitEnum.FAILED
            raise StopIteration
        path = full_paths[0]
        if not os.path.abspath(path):
            self.ErrorCode(pk.ErrorEnum.NOT_SUPPORTED,
                           "Path is not absolute: %s")
            self.exit = pk.ExitEnum.FAILED
            raise StopIteration
        if not os.path.isfile(path):
            self.ErrorCode(pk.ErrorEnum.INVALID_PACKAGE_FILE,
                           "File doesn't exist: %s" % path)
            self.exit = pk.ExitEnum.FAILED
            raise StopIteration

        kwargs = {"path": path,
                  "force": True}
        self.trans = self._get_merged_trans(aptd_enums.ROLE_INSTALL_FILE,
                                            kwargs=kwargs)
        yield self.trans._run(sender)

    @dbus_deferred_method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                          in_signature="uss", out_signature="",
                          sender_keyword="sender")
    def InstallSignature(self, sig_type, key_id, package_id, sender):
        """This method allows us to install new security keys.

        :param sig_type: A key type, e.g. gpg
        :param key_id: A key ID, e.g. BB7576AC
        :param package_id:
            A PackageID for the package that the user is trying to install
            (ignored)
        """
        pklog.info("InstallSignature() was called: %s", str(key_id))
        self.role = pk.RoleEnum.INSTALL_SIGNATURE
        kwargs = {"sig_type": sig_type,
                  "key_id": key_id,
                  "package_id": package_id}
        return self._run_query(kwargs, sender)

    @dbus.service.method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                         in_signature="sss", out_signature="",
                         sender_keyword="sender")
    def RepoSetData(self, repo_id, parameter, value, sender):
        """This method allows arbitary data to be passed to the repository
        handler.

        :param repo_id:
            A repository identifier, e.g. fedora-development-debuginfo
        :param parameter:
            The backend specific value, e.g. set-download-url.
        :param value:
            The backend specific value, e.g. http://foo.bar.org/baz.
        """
        pklog.info("RepoSetData() was called: %s, %s, %s",
                   str(repo_id), str(parameter), str(value))
        self.role = pk.RoleEnum.REPO_SET_DATA
        GLib.idle_add(self._fail_not_implemented)

    @dbus_deferred_method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                          in_signature="sb", out_signature="",
                          sender_keyword="sender")
    def RepoEnable(self, repo_id, enabled, sender):
        """This method enables the repository specified.

        :param repo_id:
            A repository identifier, e.g. fedora-development-debuginfo or an
            apt source ("deb http://... unstable main")
        :param enabled: true if enabled, false if disabled.
        """
        pklog.info("RepoEnable() was called(): %s, %s",
                   str(repo_id), str(enabled))
        self.role = pk.RoleEnum.REPO_ENABLE
        kwargs = {"repo_id": repo_id,
                  "enabled": enabled}
        return self._run_query(kwargs, sender)

    @dbus_deferred_method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                          in_signature="tsas", out_signature="",
                          sender_keyword="sender")
    def WhatProvides(self, filter, type, values, sender):
        """This method returns packages that provide the supplied attributes.
        This method is useful for finding out what package(s) provide a
        modalias or GStreamer codec string.

        This method typically emits Progress, Status and Error and Package.

        Package enumerated types should be available or installed.

        :param filter:
            A correct filter, e.g. none or installed;~devel
        :param type:
            A PkProvideType, e.g. PK_PROVIDES_ENUM_CODEC.
        :param values:
            The data to send to the backend to get the packages. Note: This
            is backend specific.
        """
        pklog.info("WhatProvides() was called")
        self.role = pk.RoleEnum.WHAT_PROVIDES
        kwargs = {"filters": filter,
                  "provides_type": type,
                  "values": values}
        return self._run_query(kwargs, sender)

    @dbus.service.method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                         in_signature="", out_signature="",
                         sender_keyword="sender")
    def GetCategories(self, sender):
        pklog.info("GetCategories() was called")
        """This method return the collection categories"""
        self.role = pk.RoleEnum.GET_CATEGORIES
        GLib.idle_add(self._fail_not_implemented)

    @dbus_deferred_method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                          in_signature="tasb", out_signature="",
                          sender_keyword="sender")
    def GetRequires(self, filter, package_ids, recursive, sender):
        """This method returns packages that depend on this package. This is
        useful to know, as if package_id is being removed, we can warn the
        user what else would be removed.

        This method typically emits Progress, Status and Error and Package.

        Package enumerated types should be available or installed.

        :param filter: A correct filter, e.g. none or installed;~devel
        :param package_ids: An array of package IDs.
        :param recursive:
            Either true or false. If yes then the requirements should be
            returned for all packages returned. This means if
            gnome-power-manager depends on NetworkManager and NetworkManager
            depends on HAL, then GetRequires on HAL should return both
            gnome-power-manager and NetworkManager.
        """
        pklog.info("GetRequires() was called")
        self.role = pk.RoleEnum.GET_REQUIRES
        kwargs = {"filters": filter,
                  "package_ids": package_ids,
                  "recursive": recursive}
        return self._run_query(kwargs, sender)

    @dbus_deferred_method(PACKAGEKIT_TRANS_DBUS_INTERFACE,
                          in_signature="tasb", out_signature="",
                          sender_keyword="sender")
    def GetDepends(self, filter, package_ids, recursive, sender):
        """This method returns packages that this package depends on.

        This method typically emits Progress, Status and Error and Package.

        Package enumerated types should be available or installed.

        :param filter: A correct filter, e.g. none or installed;~devel
        :param package_ids: An array of package IDs.
        :param recursive:
            Either true or false. If yes then the requirements should be
            returned for all packages returned. This means if
            gnome-power-manager depends on NetworkManager and NetworkManager
            depends on HAL, then GetDepends on gnome-power-manager should
            return both HAL and NetworkManager.
        """
        pklog.info("GetDepends() was called")
        self.role = pk.RoleEnum.GET_DEPENDS
        kwargs = {"filters": filter,
                  "package_ids": package_ids,
                  "recursive": recursive}
        return self._run_query(kwargs, sender)

    # HELPERS

    def _fail_not_implemented(self):
        self.ErrorCode(pk.ErrorEnum.NOT_SUPPORTED, "Unimplemented method")
        self.exit = pk.ExitEnum.FAILED
        return False

    def _get_properties(self, iface):
        """Helper to get the properties of a D-Bus interface."""
        if iface == PACKAGEKIT_TRANS_DBUS_INTERFACE:
            return {"Role": dbus.UInt32(self.role),
                    "Status": dbus.UInt32(self.status),
                    "LastPackage": dbus.String(self.last_package),
                    "Uid": dbus.UInt32(self.uid),
                    "Percentage": dbus.UInt32(self.percentage),
                    "AllowCancel": dbus.Boolean(self.allow_cancel),
                    "CallerActive": dbus.Boolean(self.caller_active),
                    "ElapsedTime": dbus.UInt32(self.elapsed_time),
                    "RemainingTime": dbus.UInt32(self.remaining_time),
                    "DownloadSizeRemaining": dbus.UInt64(
                        self.download_size_remaining),
                    "TransactionFlags": dbus.UInt64(self.flags),
                    "Speed": dbus.UInt32(self.speed)
                    }
        else:
            return {}

    @inline_callbacks
    def _run_query(self, kwargs, sender):
        self.trans = self._get_merged_trans(aptd_enums.ROLE_PK_QUERY,
                                            kwargs=kwargs)
        yield self.trans._run(sender)

    def _get_aptd_package_id(self, pk_id):
        """Convert a PackageKit Package ID to the apt syntax.
        e.g. xterm;235;i386;installed to xterm:i386=235
        """
        name, version, arch, data = pk_id.split(";")
        id = name
        if arch != self.queue.worker.NATIVE_ARCH and arch != "all":
            id += ":%s" % arch
        if version:
            id += "=%s" % version
        if data and data not in ["local", "installed"]:
            id += "/%s" % data
        return id

    def _get_merged_trans(self, role, pkg_ids=None, pkg_type=None,
                          kwargs=None):
        if pkg_ids:
            packages = [[], [], [], [], [], []]
            packages[pkg_type] = [self._get_aptd_package_id(pkg)
                                  for pkg in pkg_ids]
        else:
            packages = None
        if self.trans:
            raise Exception("%s: Transaction may only run once." %
                            pk.ErrorEnum.TRANSACTION_FAILED)
        trans = MergedTransaction(self, role, self.queue,
                                  packages=packages, kwargs=kwargs)
        try:
            trans._set_locale(self.hints["locale"])
        except (KeyError, ValueError):
            # If the locale isn't vaild or supported a ValueError
            # will be raised
            pass
        try:
            trans._set_debconf(self.hints["frontend-socket"])
        except KeyError:
            pass
        self.queue.limbo[trans.tid] = trans
        return trans


if META_RELEASE_SUPPORT:

    class GMetaRelease(GObject.GObject, MetaReleaseCore):

        __gsignals__ = {"download-done": (GObject.SignalFlags.RUN_FIRST,
                                          None,
                                          ())}

        def __init__(self):
            GObject.GObject.__init__(self)
            MetaReleaseCore.__init__(self, False, False)

        def download(self):
            MetaReleaseCore.download(self)
            self.emit("download-done")


def get_pk_exit_enum(enum):
    try:
        return MAP_EXIT_ENUM[enum]
    except KeyError:
        return pk.ExitEnum.UNKNOWN


def get_pk_status_enum(enum):
    try:
        return MAP_STATUS_ENUM[enum]
    except KeyError:
        return pk.StatusEnum.UNKNOWN


def get_pk_package_enum(enum):
    try:
        return MAP_PACKAGE_ENUM[enum]
    except KeyError:
        return pk.InfoEnum.UNKNOWN


def get_pk_error_enum(enum):
    try:
        return MAP_ERROR_ENUM[enum]
    except KeyError:
        return pk.ErrorEnum.UNKNOWN


def get_pk_package_id(pk_id, data=""):
    """Convert an AptDaemon package ID to the PackageKit syntax.
    e.g. xterm:i368=235; to xterm;235;i386;installed
    """
    # FIXME add arch support
    name, version, release = split_package_id(pk_id)
    try:
        name, arch = name.split(":", 1)
    except ValueError:
        arch = ""
    if version is None:
        version = ""
    if release is None:
        release = ""
    return "%s;%s;%s;%s" % (name, version, arch, data or release)


def defer_idle(func, *args):
    func(*args)
    return False


def get_string_from_flags(flags):
    """Return a human readable string of the applied transaction flags."""
    ret = ""
    if flags == pk.TransactionFlagEnum.NONE:
        return "simulate"
    if bitfield_contains(flags, pk.TransactionFlagEnum.SIMULATE):
        ret += " simulate"
    if bitfield_contains(flags, pk.TransactionFlagEnum.ONLY_DOWNLOAD):
        ret += " only-download"
    if bitfield_contains(flags, pk.TransactionFlagEnum.ONLY_TRUSTED):
        ret += " only-trusted"
    return ret.strip()


def get_string_from_array(array):
    """Convert a DBus Array to a human readable format"""
    return [str(value) for value in array]


# vim: ts=4 et sts=4
