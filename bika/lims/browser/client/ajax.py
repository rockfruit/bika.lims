# -*- coding: utf-8 -*-
#
# This file is part of Bika LIMS
#
# Copyright 2011-2016 by it's authors.
# Some rights reserved. See LICENSE.txt, AUTHORS.txt.

import json

import plone
from Products.CMFCore.utils import getToolByName

from bika.lims.adapters.referencewidgetvocabulary import DefaultReferenceWidgetVocabulary
from bika.lims.browser import BrowserView
from bika.lims.utils import JSONEncoder


class ReferenceWidgetVocabulary(DefaultReferenceWidgetVocabulary):
    def __call__(self):
        base_query = json.loads(self.request['base_query'])
        portal_type = base_query.get('portal_type', [])
        if 'Contact' in portal_type:
            base_query['getParentUID'] = [self.context.UID(), ]
        self.request['base_query'] = json.dumps(base_query, cls=JSONEncoder)
        return DefaultReferenceWidgetVocabulary.__call__(self)


class ajaxGetClientInfo(BrowserView):
    def __call__(self):
        plone.protect.CheckAuthenticator(self.request)
        wf = getToolByName(self.context, 'portal_workflow')
        ret = {'ClientTitle': self.context.Title(),
               'ClientID': self.context.getClientID(),
               'ClientSysID': self.context.id,
               'ClientUID': self.context.UID(),
               'ContactUIDs': [c.UID() for c in
                               self.context.objectValues('Contact') if
                               wf.getInfoFor(c, 'inactive_state',
                                             '') == 'active']
               }

        return json.dumps(ret)
