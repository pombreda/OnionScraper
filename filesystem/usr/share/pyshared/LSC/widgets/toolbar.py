#!/usr/bin/env python
# -*- coding:UTF-8 -*-
#       Copyright (c) Stephen Smally <stephen.smally@gmail.com>
#
#       This program is free software; you can redistribute it and/or modify
#       it under the terms of the GNU General Public License as published by
#       the Free Software Foundation; either version 2 of the License, or
#       (at your option) any later version.
#       This program is distributed in the hope that it will be useful,
#       but WITHOUT ANY WARRANTY; without even the implied warranty of
#       MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#       GNU General Public License for more details.
#       You should have received a copy of the GNU General Public License
#       along with this program; if not, write to the Free Software
#       Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#       MA 02110-1301, USA.
#

from gi.repository import Gtk
import searchentry


class Toolbar(Gtk.Toolbar):
    def __init__(self):
        super(Toolbar, self).__init__()
        self.set_style(Gtk.ToolbarStyle.BOTH_HORIZ)
        self.settings = Gtk.ToolButton()
        self.settings.set_stock_id(Gtk.STOCK_PREFERENCES)
        self.set_icon_size(Gtk.IconSize.SMALL_TOOLBAR)
        self.box = Gtk.HBox()
        self.box.set_spacing(5)
        self.vbox = Gtk.VBox()
        for items in self.back_forwards():
            self.insert(items, -1)

    def back_forwards(self):
        self.back = Gtk.ToolButton()
        self.back.set_stock_id(Gtk.STOCK_GO_BACK)
        self.back.set_is_important(False)
        self.back.set_sensitive(False)
        self.space = Gtk.SeparatorToolItem()
        return (self.back,)

    def add_sections(self, seclist=[], important=True, func=None):
        sectionslist = {}
        self.group = Gtk.RadioButton()
        self.group.set_relief(Gtk.ReliefStyle.NONE)
        self.group.set_can_focus(False)
        self.group_box = Gtk.HBox()
        self.group_box.set_spacing(2)
        self.group_icon = Gtk.Image()
        self.group.label = Gtk.Label()
        self.group_icon.set_from_icon_name(
            seclist[0][0], Gtk.IconSize.SMALL_TOOLBAR)
        self.group.label.set_text(seclist[0][1])
        self.group_box.pack_start(self.group_icon, False, False, 0)
        self.group_box.pack_start(self.group.label, False, False, 0)
        self.group.add(self.group_box)
        self.group.connect("toggled", func, self)
        self.group.set_property("draw-indicator", False)
        self.box.pack_start(self.group, False, False, 0)
        sectionslist[self.group] = seclist[0][2]
        for (icon, name, action) in seclist[1:]:
            self.choose = Gtk.RadioButton(group=self.group)
            self.choose.set_relief(Gtk.ReliefStyle.NONE)
            self.choose.set_can_focus(False)
            self.choose_box = Gtk.HBox()
            self.choose_box.set_spacing(2)
            self.choose_icon = Gtk.Image()
            self.choose.label = Gtk.Label()
            self.choose_icon.set_from_icon_name(
                icon, Gtk.IconSize.SMALL_TOOLBAR)
            self.choose.label.set_text(name)
            self.choose_box.pack_start(self.choose_icon, False, False, 0)
            self.choose_box.pack_start(self.choose.label, False, False, 0)
            self.choose.add(self.choose_box)
            self.choose.connect("toggled", func, self)
            self.choose.set_property("draw-indicator", False)
            self.box.pack_start(self.choose, False, False, 0)
            sectionslist[self.choose] = action
            if action == "basket":
                self.basket_radio = self.choose
        self.vbox.pack_start(self.box, True, False, 0)
        self.box_tool = Gtk.ToolItem()
        self.box_tool.add(self.vbox)
        self.insert(self.box_tool, -1)
        self.expander = Gtk.ToolItem()
        self.expander.set_expand(True)
        self.entry = searchentry.Entry()
        self.insert(self.expander, -1)
        self.insert(self.entry, -1)
        self.insert(self.settings, -1)
        return sectionslist

    def refresh_back_forward(self, can_home):
        self.back.set_sensitive(can_home)
