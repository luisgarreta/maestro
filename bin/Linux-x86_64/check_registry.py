# -*- coding: utf-8 -*-
"""
 Check Registry on Windows
 Copyright Schrodinger, LLC. All rights reserved.
"""

import winreg


def check_compatibilty_mode(mae_exe):
    """
    Windows specific function
    tells if Maestro runs in compatibility mode
    checks in Windows registry if Maestro configured to run in compatibility mode

    :param mae_exe: maestro executable with the full path
    :type mae_exe: string

    :rtype Boolean
    """
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r'Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers'
        )
    except EnvironmentError:
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r'Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers'
            )
        except EnvironmentError:
            return False

    info_key = winreg.QueryInfoKey(key)
    num_values = info_key[1]

    for index in range(num_values):
        value = winreg.EnumValue(key, index)
        if value[0] == mae_exe and (value[1].find("WIN8RTM") != -1 or
                                    value[1].find("WIN7RTM") != -1):
            return True

    winreg.CloseKey(key)

    return False
