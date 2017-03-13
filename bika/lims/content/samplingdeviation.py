# -*- coding: utf-8 -*-
#
# This file is part of Bika LIMS
#
# Copyright 2011-2017 by it's authors.
# Some rights reserved. See LICENSE.txt, AUTHORS.txt.

from AccessControl import ClassSecurityInfo
from Products.Archetypes.public import *

from bika.lims.config import PROJECTNAME
from bika.lims.content.bikaschema import BikaSchema

schema = BikaSchema.copy() + Schema((

))

schema['description'].schemata = 'default'
schema['description'].widget.visible = True


class SamplingDeviation(BaseFolder):
    security = ClassSecurityInfo()
    displayContentsTab = False
    schema = schema

    _at_rename_after_creation = True

    def _renameAfterCreation(self, check_auto_id=False):
        from bika.lims.idserver import renameAfterCreation
        renameAfterCreation(self)


registerType(SamplingDeviation, PROJECTNAME)
