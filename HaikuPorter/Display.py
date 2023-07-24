# -*- coding: utf-8 -*-
#
# Copyright 2016 Jerome Duval
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

import curses
import datetime
import time


class DisplayContext(object):
    def __init__(self):
        self.stdscr = None

    def __enter__(self):
        self.stdscr = curses.initscr()
        curses.noecho()
        curses.cbreak()
        self.stdscr.keypad(1)
        try:
            curses.start_color()
            curses.curs_set(0)
        except:
            pass
        return self

    def __exit__(self, ignoredType, value, traceback):
        if self.stdscr:
            curses.curs_set(2)
            self.stdscr.keypad(0)
            curses.echo()
            curses.nocbreak()
            curses.endwin()


class Display(object):
    def __init__(self, stdscr, builders_used):
        self.builders_used = builders_used

        termsize = stdscr.getmaxyx()
        y, x = termsize
        ncols = 80

        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_BLACK)
        curses.init_pair(6, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(7, curses.COLOR_BLUE, curses.COLOR_BLACK)
        curses.init_pair(8, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
        curses.init_pair(9, curses.COLOR_BLUE, curses.COLOR_WHITE)
        self.c_standard = curses.color_pair(1)
        self.c_success = curses.color_pair(2)
        self.c_failure = curses.color_pair(3)
        self.c_lost = curses.color_pair(4)
        self.c_blocked = curses.color_pair(5)
        self.c_sumlabel = curses.color_pair(6) | curses.A_BOLD
        self.c_dashes = curses.color_pair(7) | curses.A_BOLD
        self.c_duration = curses.color_pair(4)
        self.c_tableheader = curses.color_pair(1)
        self.c_portname = curses.color_pair(6)
        self.c_bldphase = curses.color_pair(4)
        self.c_shutdown = curses.color_pair(1)
        self.c_advisory = curses.color_pair(4)

        self.c_slave = []
        self.c_slave.append(curses.color_pair(1) | curses.A_BOLD)
        self.c_slave.append(curses.color_pair(2) | curses.A_BOLD)
        self.c_slave.append(curses.color_pair(4) | curses.A_BOLD)
        self.c_slave.append(curses.color_pair(8) | curses.A_BOLD)
        self.c_slave.append(curses.color_pair(3) | curses.A_BOLD)
        self.c_slave.append(curses.color_pair(7) | curses.A_BOLD)
        self.c_slave.append(curses.color_pair(6) | curses.A_BOLD)
        self.c_slave.append(curses.color_pair(5) | curses.A_BOLD)
        self.c_slave.append(curses.color_pair(1))
        self.c_slave.append(curses.color_pair(2))
        self.c_slave.append(curses.color_pair(4))
        self.c_slave.append(curses.color_pair(8))
        self.c_slave.append(curses.color_pair(3))
        self.c_slave.append(curses.color_pair(7))
        self.c_slave.append(curses.color_pair(6))
        self.c_slave.append(curses.color_pair(9))

        for i in range(16):
            self.c_slave.append(self.c_slave[i] | curses.A_UNDERLINE)
        for i in range(32):
            self.c_slave.append(self.c_slave[i])

        self.zone_summary = curses.newwin(2, ncols, 0, 0)
        self.zone_builders = curses.newwin(self.builders_used + 4, ncols, 2, 0)
        self.maxrows = y - (self.builders_used + 4 + 2)
        self.zone_history = curses.newwin(
            self.maxrows, ncols, self.builders_used + 4 + 2, 0
        )

        self.zone_summary.addstr(
            0,
            0,
            " Total         Built        Ignored        Load  0.00  Pkg/hour           "
            "     ",
            self.c_sumlabel,
        )
        self.zone_summary.addstr(
            1,
            0,
            "  Left        Failed        Skipped        Swap  0.0%   Impulse	     "
            " 0:00:00  ",
            self.c_sumlabel,
        )

        dashes = "=" * (ncols - 1)
        self.zone_builders.addstr(0, 0, dashes, self.c_dashes)
        self.zone_builders.addstr(2, 0, dashes, self.c_dashes)
        self.zone_builders.addstr(self.builders_used + 4 - 1, 0, dashes, self.c_dashes)

        self.zone_builders.addstr(
            1,
            0,
            " ID  Duration  Build Phase      Port Name                               "
            " Lines ",
            self.c_tableheader,
        )
        for i in range(3, self.builders_used + 4 - 1):
            self.zone_builders.addstr(i, 0, " " * ncols, self.c_standard)

        stdscr.refresh()
        self.zone_summary.refresh()
        self.zone_builders.refresh()
        self.zone_history.refresh()

    def updateSummary(self, data):
        self.zone_summary.addstr(
            0, 7, str(data["builds"]["total"]).ljust(4), self.c_standard
        )
        self.zone_summary.addstr(
            0, 21, str(data["builds"]["complete"]).ljust(4), self.c_success
        )
        self.zone_summary.addstr(
            0, 37, str(data["builds"]["blocked"]).ljust(4), self.c_blocked
        )
        self.zone_summary.addstr(0, 64, str(data["pkg_hour"]).ljust(5), self.c_standard)
        self.zone_summary.addstr(
            1,
            7,
            str(
                data["builds"]["scheduled"]
                + data["builds"]["active"]
                + data["builds"]["blocked"]
            ).ljust(4),
            self.c_standard,
        )
        self.zone_summary.addstr(
            1, 21, str(data["builds"]["failed"]).ljust(4), self.c_failure
        )
        self.zone_summary.addstr(
            0, 37, str(data["builds"]["lost"]).ljust(4), self.c_lost
        )
        self.zone_summary.addstr(1, 64, str(data["impulse"]).ljust(5), self.c_standard)
        self.zone_summary.addstr(
            1,
            70,
            (
                str(datetime.timedelta(seconds=int(data["duration"]))).zfill(8)
                if data["duration"]
                else "       "
            ),
            self.c_duration,
        )
        self.zone_summary.refresh()

    def updateBuilders(self, data):
        builders = data["builders"]["active"]
        for i in range(0, self.builders_used):
            currentBuild = builders[i]["currentBuild"]
            self.zone_builders.addstr(
                3 + i, 1, str(i + 1).zfill(2)[:2], self.c_slave[i]
            )
            if currentBuild is None:
                self.zone_builders.addstr(3 + i, 5, " " * 75, self.c_standard)
                continue
            portName = currentBuild["build"]["port"]["revisionedName"]
            self.zone_builders.addstr(
                3 + i,
                5,
                (
                    str(
                        datetime.timedelta(seconds=int(currentBuild["duration"]))
                    ).zfill(8)[:8]
                    if currentBuild["duration"]
                    else "        "
                ),
                self.c_standard,
            )
            self.zone_builders.addstr(
                3 + i, 15, currentBuild["phase"].ljust(12)[:12], self.c_bldphase
            )
            self.zone_builders.addstr(
                3 + i, 32, portName.ljust(38)[:38], self.c_portname
            )
            self.zone_builders.addstr(
                3 + i, 71, str(currentBuild["lines"]).rjust(7)[:7], self.c_standard
            )

        self.zone_builders.refresh()

    def updateHistory(self, data):
        row = 0
        for build in list(reversed(data)):
            current = build.status
            if current is None:
                self.zone_builders.addstr(row, 5, " " * 75, self.c_standard)
                continue
            self.zone_history.addstr(
                row,
                10,
                "[" + str(int(current["builderId"]) + 1).zfill(2)[:2] + "]",
                self.c_slave[int(current["builderId"])],
            )
            portName = current["port"]["revisionedName"]
            self.zone_history.addstr(
                row,
                70,
                (
                    str(datetime.timedelta(seconds=int(current["duration"]))).zfill(8)[
                        :8
                    ]
                    if current["duration"]
                    else "        "
                ),
                self.c_standard,
            )
            self.zone_history.addstr(
                row,
                15,
                "success" if current["buildSuccess"] else "failed ",
                self.c_success if current["buildSuccess"] else self.c_failure,
            )
            self.zone_history.addstr(row, 24, portName.ljust(38)[:38], self.c_portname)
            self.zone_history.addstr(
                row,
                1,
                time.strftime("%X", time.localtime(current["startTime"])),
                self.c_standard,
            )
            row += 1
            if row >= self.maxrows:
                break

        self.zone_history.refresh()
