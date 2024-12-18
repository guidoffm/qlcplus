#!/bin/bash

/Applications/QLC+.app/Contents/MacOS/qlcplus -w -p -k -f -o eins.qxw &
caffeinate -w $?

