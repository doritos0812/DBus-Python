"""DBus backed display management for Mutter"""
from collections import defaultdict
from logging import currentframe
from Xlib import display
import dbus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

DBusGMainLoop(set_as_default = True)

class DisplayMode:
    def __init__(self, mode_info):
        self.mode_info = mode_info

    def __str__(self):
        return "%sx%s@%s" % (self.width, self.height, self.frequency)

    def mode_id(self):
        return self.mode_info[0]

    @property
    def width(self):
        """width in physical pixels"""
        return self.mode_info[1]

    @property
    def height(self):
        """height in physical pixels"""
        return self.mode_info[2]

    @property
    def frequency(self):
        """refresh rate"""
        return self.mode_info[3]

    @property
    def scale(self):
        """scale preferred as per calculations"""
        return self.mode_info[4]

    @property
    def supported_scale(self):
        """scales supported by this mode"""
        return self.mode_info[5]

    @property
    def properties(self):
        """optional properties"""
        return self.mode_info[6]

    def is_current(self):
        """Return True if the mode is the current one"""
        return "is-current" in self.properties


class DisplayConfig():
    """Class to interact with the Mutter.DisplayConfig service"""
    namespace = "org.gnome.Mutter.DisplayConfig"
    dbus_path = "/org/gnome/Mutter/DisplayConfig"

    # Methods used in ApplyMonitorConfig
    VERIFY_METHOD = 0
    TEMPORARY_METHOD = 1
    PERSISTENT_METHOD = 2

    def __init__(self):
        session_bus = dbus.SessionBus()
        proxy_obj = session_bus.get_object(self.namespace, self.dbus_path)
        self.interface = dbus.Interface(proxy_obj, dbus_interface=self.namespace)
        self.resources = self.interface.GetResources()
        self.current_state = self.interface.GetCurrentState()
        self.config_serial = self.current_state[0]

    @property
    def serial(self):
        """
        @serial is an unique identifier representing the current state
        of the screen. It must be passed back to ApplyConfiguration()
        and will be increased for every configuration change (so that
        mutter can detect that the new configuration is based on old
        state)
        """
        return self.resources[0]

    @property
    def crtcs(self):
        """
        A CRTC (CRT controller) is a logical monitor, ie a portion
        of the compositor coordinate space. It might correspond
        to multiple monitors, when in clone mode, but not that
        it is possible to implement clone mode also by setting different
        CRTCs to the same coordinates.

        The number of CRTCs represent the maximum number of monitors
        that can be set to expand and it is a HW constraint; if more
        monitors are connected, then necessarily some will clone. This
        is complementary to the concept of the encoder (not exposed in
        the API), which groups outputs that necessarily will show the
        same image (again a HW constraint).

        A CRTC is represented by a DBus structure with the following
        layout:
        * u ID: the ID in the API of this CRTC
        * x winsys_id: the low-level ID of this CRTC (which might
                    be a XID, a KMS handle or something entirely
                    different)
        * i x, y, width, height: the geometry of this CRTC
                                (might be invalid if the CRTC is not in
                                use)
        * i current_mode: the current mode of the CRTC, or -1 if this
                        CRTC is not used
                        Note: the size of the mode will always correspond
                        to the width and height of the CRTC
        * u current_transform: the current transform (espressed according
                            to the wayland protocol)
        * au transforms: all possible transforms
        * a{sv} properties: other high-level properties that affect this
                            CRTC; they are not necessarily reflected in
                            the hardware.
                            No property is specified in this version of the API.

        Note: all geometry information refers to the untransformed
        display.
        """
        return self.resources[1]

    @property
    def outputs(self):
        """
        An output represents a physical screen, connected somewhere to
        the computer. Floating connectors are not exposed in the API.
        An output is a DBus struct with the following fields:
        * u ID: the ID in the API
        * x winsys_id: the low-level ID of this output (XID or KMS handle)
        * i current_crtc: the CRTC that is currently driving this output,
                          or -1 if the output is disabled
        * au possible_crtcs: all CRTCs that can control this output
        * s name: the name of the connector to which the output is attached
                  (like VGA1 or HDMI)
        * au modes: valid modes for this output
        * au clones: valid clones for this output, ie other outputs that
                     can be assigned the same CRTC as this one; if you
                     want to mirror two outputs that don't have each other
                     in the clone list, you must configure two different
                     CRTCs for the same geometry
        * a{sv} properties: other high-level properties that affect this
                            output; they are not necessarily reflected in
                            the hardware.
                            Known properties:
                            - "vendor" (s): (readonly) the human readable name
                                            of the manufacturer
                            - "product" (s): (readonly) the human readable name
                                             of the display model
                            - "serial" (s): (readonly) the serial number of this
                                            particular hardware part
                            - "display-name" (s): (readonly) a human readable name
                                                  of this output, to be shown in the UI
                            - "backlight" (i): (readonly, use the specific interface)
                                               the backlight value as a percentage
                                               (-1 if not supported)
                            - "primary" (b): whether this output is primary
                                             or not
                            - "presentation" (b): whether this output is
                                                  for presentation only
                            Note: properties might be ignored if not consistenly
                            applied to all outputs in the same clone group. In
                            general, it's expected that presentation or primary
                            outputs will not be cloned.
        """
        return self.resources[2]

    @property
    def modes(self):
        """
        A mode represents a set of parameters that are applied to
        each output, such as resolution and refresh rate. It is a separate
        object so that it can be referenced by CRTCs and outputs.
        Multiple outputs in the same CRTCs must all have the same mode.
        A mode is exposed as:
        * u ID: the ID in the API
        * x winsys_id: the low-level ID of this mode
        * u width, height: the resolution
        * d frequency: refresh rate
        * u flags: mode flags as defined in xf86drmMode.h and randr.h

        Output and modes are read-only objects (except for output properties),
        they can change only in accordance to HW changes (such as hotplugging
        a monitor), while CRTCs can be changed with ApplyConfiguration().

        XXX: actually, if you insist enough, you can add new modes
        through xrandr command line or the KMS API, overriding what the
        kernel driver and the EDID say.
        Usually, it only matters with old cards with broken drivers, or
        old monitors with broken EDIDs, but it happens more often with
        projectors (if for example the kernel driver doesn't add the
        640x480 - 800x600 - 1024x768 default modes). Probably something
        that we need to handle in mutter anyway.
        """
        return self.resources[3]

    @property
    def max_screen_width(self):
        return self.resources[4]

    @property
    def max_screen_height(self):
        return self.resources[5]

    
    def available_modes(self, monitor):
        # print("Available Monitor Modes")
        modes = monitor[1]
        mode_list = [str(mode[0]) for mode in modes]
        return mode_list



    def print_monitor_config(self, monitor):
        print("Print Monitor Config")
        monitor_info, modes, props = monitor
        print(' '.join(monitor_info))
        for mode in modes:
            # print(mode[0])
            d_mode = DisplayMode(mode)
            if d_mode.is_current():
                print("Current: ",str(d_mode))
        print(props)

    # def print_monitor_resources(self, monitor):
    #     print("Print Monitor Resources")
    #     print(monitor[0])
    #     print(monitor[1])
    #     print(monitor[2])
    #     print(monitor[3])
    #     print(monitor[4])
    #     print(monitor[5])
    #     print(monitor[6])
    #     print(monitor[7])
    #     print(monitor[8])
    #     print(monitor[9])



    def print_current_state(self):
        serial, monitors, logical_monitors, properties = self.current_state
        # for val in self.current_state:
        #     print(val)
        # print('------------------------')
        print("Serial: %s" % serial)
        print("Monitors num:",len(monitors))
        for monitor in monitors:
            print("Available Monitor Modes")
            print(self.available_modes(monitor))
            self.print_monitor_config(monitor)
        print("Logical monitors")
        for monitor in logical_monitors:
            print(monitor)
        print("PROPS")
        for prop in properties:
            print("%s: %s" % (prop, properties[prop]))

    # def print_resources(self):
    #     print(len(self.resources))
    #     serial, monitors, logical_monitors, properties, max_screen_width, max_screen_height = self.resources
    #     print("Serial: %s" % serial)
    #     print("Monitors")
    #     for monitor in monitors:
    #         print(monitor)
    #         self.print_monitor_resources(monitor)
    #     print("Logical monitors")
    #     for monitor in logical_monitors:
    #         print(monitor)
    #     print("PROPS")
    #     for prop in properties:
    #         print("%s: %s" % (prop, properties[prop]))

    def apply_monitors_config(self):
        scale = dbus.Double(1.0)
        transform = dbus.UInt32(0)
        is_primary = True
        monitors = [
            [
                0,
                0,
                scale,
                transform,
                is_primary,
                [[dbus.String('DP-1'), dbus.String('1920x1200@59.950172424316406'), {}]]
            ],
            # [
            #     1920,
            #     0,
            #     scale,
            #     transform,
            #     False,
            #     [[dbus.String('HDMI-1'), dbus.String('1920x1200@59.950172424316406'), {}]]
            # ]
        ]
        self.interface.ApplyMonitorsConfig(
            self.config_serial,
            1,
            monitors,
            {}
        )
    
    def single_mode(self, x_position, y_position, scale, transform, is_primary, monitor_list):
        monitors = [
            [
                x_position,
                y_position,
                scale,
                transform,
                is_primary,
                monitor_list
            ]
        ]
    
    def extand_mode(self, x_position, y_position, scale, transform, is_primary, monitor_list):
        monitors = [
            [
                x_position,
                y_position,
                scale,
                transform,
                is_primary,
                monitor_list
            ]
        ]

    def clone_mode(self, x_position, y_position, scale, transform, is_primary, monitor_list):
        monitors = [
            [
                x_position,
                y_position,
                scale,
                transform,
                is_primary,
                monitor_list
            ]
        ]


if __name__ == "__main__":
    display_config = DisplayConfig()
    # display_config.print_monitor()
    display_config.print_current_state()

    # print('====================')
    # display_config.print_resources()
    # display_config.apply_monitors_config()
    # display_config = DisplayConfig()





    # # --------- DBus Loop -----------
    # def catchcall_signal_handler(*args, **kwargs):
    #     display_config = DisplayConfig()
    #     display_config.print_current_state()
        

    # bus = dbus.SessionBus()
    # bus.add_signal_receiver(catchcall_signal_handler, dbus_interface="org.gnome.Mutter.DisplayConfig", signal_name='MonitorsChanged')

    # loop = GLib.MainLoop()
    # loop.run()
