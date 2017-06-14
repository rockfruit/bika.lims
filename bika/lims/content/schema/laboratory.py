# This file is part of Bika LIMS
#
# Copyright 2011-2016 by it's authors.
# Some rights reserved. See LICENSE.txt, AUTHORS.txt.
from Products.Archetypes.Field import BooleanField, IntegerField, StringField, \
    TextField
from Products.Archetypes.Schema import Schema
from Products.Archetypes.Widget import BooleanWidget, ImageWidget, \
    StringWidget, TextAreaWidget
from bika.lims import bikaMessageFactory as _
from bika.lims.browser.widgets import IntegerWidget
from bika.lims.config import ManageBika
from bika.lims.content.organisation import Organisation
from bika.lims.content.schema import Storage
from plone.app.blob.field import ImageField

LabURL = StringField(
    'LabURL',
    storage=Storage(),
    schemata='Address',
    write_permission=ManageBika,
    widget=StringWidget(
        size=60,
        label=_("Lab URL"),
        description=_("The Laboratory's web address")
    ),
)

Confidence = IntegerField(
    'Confidence',
    storage=Storage(),
    schemata='Accreditation',
    widget=IntegerWidget(
        label=_("Confidence Level %"),
        description=_(
            "This value is reported at the bottom of all published results")
    ),
)

LaboratoryAccredited = BooleanField(
    'LaboratoryAccredited',
    storage=Storage(),
    default=False,
    schemata='Accreditation',
    write_permission=ManageBika,
    widget=BooleanWidget(
        label=_("Laboratory Accredited"),
        description=_("Check this box if your laboratory is accredited")
    ),
)

AccreditationBody = StringField(
    'AccreditationBody',
    storage=Storage(),
    schemata='Accreditation',
    write_permission=ManageBika,
    widget=StringWidget(
        label=_("Accreditation Body Abbreviation"),
        description=_("E.g. SANAS, APLAC, etc.")
    ),
)

AccreditationBodyURL = StringField(
    'AccreditationBodyURL',
    storage=Storage(),
    schemata='Accreditation',
    write_permission=ManageBika,
    widget=StringWidget(
        label=_("Accreditation Body URL"),
        description=_("Web address for the accreditation body")
    ),
)

Accreditation = StringField(
    'Accreditation',
    storage=Storage(),
    schemata='Accreditation',
    write_permission=ManageBika,
    widget=StringWidget(
        label=_("Accreditation"),
        description=_("The accreditation standard that applies, e.g. ISO 17025")
    ),
)

AccreditationReference = StringField(
    'AccreditationReference',
    storage=Storage(),
    schemata='Accreditation',
    write_permission=ManageBika,
    widget=StringWidget(
        label=_("Accreditation Reference"),
        description=_(
            "The reference code issued to the lab by the accreditation body")
    ),
)

AccreditationBodyLogo = ImageField(
    'AccreditationBodyLogo',
    storage=Storage(),
    schemata='Accreditation',
    widget=ImageWidget(
        label=_("Accreditation Logo"),
        description=_(
            "Please upload the logo you are authorised to use on your website "
            "and results reports by your accreditation body. Maximum size is "
            "175 x 175 pixels.")
    ),
)

AccreditationPageHeader = TextField(
    'AccreditationPageHeader',
    storage=Storage(),
    schemata='Accreditation',
    default="${lab_name} has been accredited as ${accreditation_standard} "
            "conformant by ${accreditation_body_abbr}, "
            "${accreditation_body_name}<br/><br/>${accreditation_body_abbr} "
            "is the single national accreditation body assessing testing and "
            "calibration laboratories for compliance to the ISO/IEC 17025 "
            "standard.<br/></br/>\nThe following analysis services have been "
            "included in the ${accreditation_body_abbr} schedule of "
            "Accreditation for this Laboratory:",
    widget=TextAreaWidget(
        label=_("Accreditation page header"),
        description=_(
            "Enter the details of your lab's service accreditations here.  "
            "The following fields are available:  lab_is_accredited, "
            "lab_name, lab_country, confidence, accreditation_body_name, "
            "accreditation_standard, accreditation_reference<br/>"),
        rows=10
    ),
)

schema = Organisation.schema.copy() + Schema((
    LabURL,
    Confidence,
    LaboratoryAccredited,
    AccreditationBody,
    AccreditationBodyURL,
    Accreditation,
    AccreditationReference,
    AccreditationBodyLogo,
    AccreditationPageHeader
))

IdField = schema['id']
IdField.widget.visible = {'edit': 'hidden', 'view': 'invisible'}

schema['Name'].validators = ()
# Update the validation layer after change the validator in runtime
schema['Name']._validationLayer()