# -*- coding: utf-8 -*-
#
# This file is part of Bika LIMS
#
# Copyright 2011-2017 by it's authors.
# Some rights reserved. See LICENSE.txt, AUTHORS.txt.

from zope.component import adapts
from zope.interface import implements

from bika.lims.interfaces import IJSONReadExtender, IAnalysisProfile


class JSONReadExtender(object):
    """- Place additional information about profile services
    into the returned records.
    Used in AR Add to prevent extra requests
    """

    implements(IJSONReadExtender)
    adapts(IAnalysisProfile)

    def __init__(self, context):
        self.context = context

    def __call__(self, request, data):
        service_data = []
        for service in self.context.getService():
            this_service = {'UID': service.UID(),
                            'Title': service.Title(),
                            'Keyword': service.getKeyword(),
                            'Price': service.getPrice(),
                            'VAT': service.getVAT(),
                            'PointOfCapture': service.getPointOfCapture(),
                            'CategoryTitle': service.getCategory().Title()}
            service_data.append(this_service)
        data['service_data'] = service_data

