'''
Simply Import DisplayMode & DisplayConfig
'''

from application import DisplayMode
from application import DisplayConfig

from collections import defaultdict
from logging import currentframe
from Xlib import display
import dbus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

DBusGMainLoop(set_as_default = True)

def catchcall_signal_handler(*args, **kwargs):
    display_config = DisplayConfig()
    # display_config.print_current_state()
    print(display_config.monitors_count)

display_config = DisplayConfig()

bus = dbus.SessionBus()
bus.add_signal_receiver(catchcall_signal_handler, dbus_interface="org.gnome.Mutter.DisplayConfig", signal_name='MonitorsChanged')

loop = GLib.MainLoop()
loop.run()