#
# This is the system Maestro command startup script - it is located in
# $MMRESDIR/maestro.cmd. This defaults to the 
# $SCHRODINGER/maestro-vXXXXX/data/res directory.  MMRESDIR can also
# be set as an environment variable to point the program to use
# a different "system" directory.  If none is set, the above
# default value is selected automatically.
#
# Any commands which are in the system file are executed when the program
# begins. Individual users may also have a maestro.cmd file in their 
# '<mmfile_schrodinger_appdata_dir>/maestro##' directory. 
# <mmfile_schrodinger_appdata_dir> = $HOME/.schrodinger (Linux)
# <mmfile_schrodinger_appdata_dir> = %APPDATA%/Schrodinger (Windows)
# The formats of the files are the same.  The commands in the user's file will
# be executed after those in the "system" file and can therefore be used to
# override the commands in this file.
#
# Format - any lines which begin with a "#" are
# ignored. All other lines must contain valid Maestro commands.
# set default force field to MMFF:
potential field=opls2005
#set the default colorscheme to "element"
colorscheme scheme=Element
#set the default ribbon color scheme to by position:
ribbon  scheme=residueposition
