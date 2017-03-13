# -*- coding: utf-8 -*-
#
# This file is part of Bika LIMS
#
# Copyright 2011-2016 by it's authors.
# Some rights reserved. See LICENSE.txt, AUTHORS.txt.

from Products.CMFPlone.utils import base_hasattr, safe_callable, isIDAutoGenerated, \
    getEmptyTitle, safe_unicode
from zope.i18nmessageid import MessageFactory

from bika.lims.utils import t

_marker = []

def _pretty_title_or_id(context, obj, empty_value=_marker):
    """Return the best possible title or id of an item, regardless
       of whether obj is a catalog brain or an object, but returning an
       empty title marker if the id is not set (i.e. it's auto-generated).
    """
    # if safe_hasattr(obj, 'aq_explicit'):
    #    obj = obj.aq_explicit
    #title = getattr(obj, 'Title', None)
    title = None
    if base_hasattr(obj, 'Title'):
        title = getattr(obj, 'Title', None)
    if safe_callable(title):
        title = title()
    if title:
        return title
    item_id = getattr(obj, 'getId', None)
    if safe_callable(item_id):
        item_id = item_id()
    if item_id and not isIDAutoGenerated(context, item_id):
        return item_id
    if empty_value is _marker:
        empty_value = getEmptyTitle(context)
    return empty_value

def pretty_title_or_id(context, obj, empty_value=_marker, domain='plone'):
    _ = MessageFactory(domain)
    title = _pretty_title_or_id(context, obj, empty_value=_marker)
    return t(context.translate(_(safe_unicode(title))))
