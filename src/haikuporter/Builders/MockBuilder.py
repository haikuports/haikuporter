# -*- coding: utf-8 -*-
#
# Copyright 2015 Michael Lotz
# Copyright 2016 Jerome Duval
# Distributed under the terms of the MIT License.


class MockBuilder(object):
    def __init__(self, name, buildFailInterval, builderFailInterval, lostAfter):
        self.name = name
        self.buildCount = 0
        self.failedBuilds = 0
        self.buildFailInterval = buildFailInterval
        self.builderFailInterval = builderFailInterval
        self.lostAfter = lostAfter
        self.lost = False
        self.currentBuild = None

    def setBuild(self, scheduledBuild, buildNumber):
        self.currentBuild = {"build": scheduledBuild.status, "number": buildNumber}

    def unsetBuild(self):
        self.currentBuild = None

    def runBuild(self):
        buildSuccess = False
        reschedule = True

        try:
            self.buildCount += 1
            if self.buildCount >= self.lostAfter:
                self.lost = True
                time.sleep(1)
                raise Exception("lost")

            buildSuccess = self.buildCount % self.buildFailInterval != 0
            if not buildSuccess:
                time.sleep(1)
                self.failedBuilds += 1
                reschedule = self.failedBuilds % self.builderFailInterval == 0
                raise Exception("failed")

            time.sleep(1)
        except Exception as exception:
            pass

        return (buildSuccess, reschedule)

    @property
    def status(self):
        return {
            "name": self.name,
            "lost": self.lost,
        }
