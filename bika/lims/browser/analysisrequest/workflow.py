from AccessControl import getSecurityManager
from bika.lims import bikaMessageFactory as _
from bika.lims import PMF
from bika.lims.browser.bika_listing import WorkflowAction
from bika.lims.browser.publish import doPublish
from bika.lims.content.analysisrequest import schema as AnalysisRequestSchema
from bika.lims.idserver import renameAfterCreation
from bika.lims.permissions import *
from bika.lims.subscribers import doActionFor
from bika.lims.utils import changeWorkflowState
from bika.lims.utils import encode_header
from bika.lims.utils import isActive
from bika.lims.utils import tmpID
from bika.lims.utils import to_utf8
from bika.lims.workflow import doActionFor
from DateTime import DateTime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.Utils import formataddr
from Products.Archetypes import PloneMessageFactory as PMF
from Products.Archetypes.config import REFERENCE_CATALOG
from Products.Archetypes.event import ObjectInitializedEvent
from Products.CMFCore.utils import getToolByName
from Products.CMFPlone.utils import safe_unicode

import json
import plone
import zope.event


class AnalysisRequestWorkflowAction(WorkflowAction):

    """Workflow actions taken in AnalysisRequest context.

        Sample context workflow actions also redirect here
        Applies to
            Analysis objects
            SamplePartition objects
    """

    def __call__(self):
        form = self.request.form
        plone.protect.CheckAuthenticator(form)
        workflow = getToolByName(self.context, 'portal_workflow')
        rc = getToolByName(self.context, REFERENCE_CATALOG)
        action, came_from = WorkflowAction._get_form_workflow_action(self)
        checkPermission = self.context.portal_membership.checkPermission

        # calcs.js has kept item_data and form input interim values synced,
        # so the json strings from item_data will be the same as the form values
        item_data = {}
        if 'item_data' in form:
            if isinstance(form['item_data'], list):
                for i_d in form['item_data']:
                    for i, d in json.loads(i_d).items():
                        item_data[i] = d
            else:
                item_data = json.loads(form['item_data'])

        # Sample Partitions or AR Manage Analyses: save Partition Table
        if action == "save_partitions_button":
            sample = self.context.portal_type == 'Sample' and self.context or\
                self.context.getSample()
            part_prefix = sample.getId() + "-P"

            nr_existing = len(sample.objectIds())
            nr_parts = len(form['PartTitle'][0])
            # add missing parts
            if nr_parts > nr_existing:
                for i in range(nr_parts - nr_existing):
                    _id = sample.invokeFactory('SamplePartition', id=tmpID())
                    part = sample[_id]
                    part.setDateReceived = DateTime()
                    part.processForm()
            # remove excess parts
            if nr_existing > nr_parts:
                for i in range(nr_existing - nr_parts):
                    part = sample['%s%s' % (part_prefix, nr_existing - i)]
                    for a in part.getBackReferences("AnalysisSamplePartition"):
                        a.setSamplePartition(None)
                    sample.manage_delObjects(['%s%s' % (part_prefix, nr_existing - i), ])
            # modify part container/preservation
            for part_uid, part_id in form['PartTitle'][0].items():
                part = sample["%s%s" % (part_prefix, part_id.split(part_prefix)[1])]
                part.edit(
                    Container=form['getContainer'][0][part_uid],
                    Preservation=form['getPreservation'][0][part_uid],
                )
                part.reindexObject()

            objects = WorkflowAction._get_selected_items(self)
            if not objects:
                message = self.context.translate(_("No items have been selected"))
                self.context.plone_utils.addPortalMessage(message, 'info')
                if self.context.portal_type == 'Sample':
                    # in samples his table is on 'Partitions' tab
                    self.destination_url = self.context.absolute_url() +\
                        "/partitions"
                else:
                    # in ar context this table is on 'ManageAnalyses' tab
                    self.destination_url = self.context.absolute_url() +\
                        "/analyses"
                self.request.response.redirect(self.destination_url)
                return

        # AR Manage Analyses: save Analyses
        if action == "save_analyses_button":
            ar = self.context
            sample = ar.getSample()

            objects = WorkflowAction._get_selected_items(self)
            if not objects:
                message = self.context.translate(_("No analyses have been selected"))
                self.context.plone_utils.addPortalMessage(message, 'info')
                self.destination_url = self.context.absolute_url() + "/analyses"
                self.request.response.redirect(self.destination_url)
                return

            Analyses = objects.keys()
            prices = form.get("Price", [None])[0]
            specs = {}
            if form.get("min", None):
                for service_uid in Analyses:
                    specs[service_uid] = {
                        "min": form["min"][0][service_uid],
                        "max": form["max"][0][service_uid],
                        "error": form["error"][0][service_uid]
                    }
            else:
                for service_uid in Analyses:
                    specs[service_uid] = {"min": "", "max": "", "error": ""}
            new = ar.setAnalyses(Analyses, prices=prices, specs=specs)

            # link analyses and partitions
            # If Bika Setup > Analyses > 'Display individual sample
            # partitions' is checked, no Partitions available.
            # https://github.com/bikalabs/Bika-LIMS/issues/1030
            if 'Partition' in form:
                for service_uid, service in objects.items():
                    part_id = form['Partition'][0][service_uid]
                    part = sample[part_id]
                    analysis = ar[service.getKeyword()]
                    analysis.setSamplePartition(part)
                    analysis.reindexObject()

            if new:
                for analysis in new:
                    # if the AR has progressed past sample_received, we need to bring it back.
                    ar_state = workflow.getInfoFor(ar, 'review_state')
                    if ar_state in ('attachment_due', 'to_be_verified'):
                        # Apply to AR only; we don't want this transition to cascade.
                        ar.REQUEST['workflow_skiplist'].append("retract all analyses")
                        workflow.doActionFor(ar, 'retract')
                        ar.REQUEST['workflow_skiplist'].remove("retract all analyses")
                        ar_state = workflow.getInfoFor(ar, 'review_state')
                    # Then we need to forward new analyses state
                    analysis.updateDueDate()
                    changeWorkflowState(analysis, 'bika_analysis_workflow', ar_state)

            message = self.context.translate(PMF("Changes saved."))
            self.context.plone_utils.addPortalMessage(message, 'info')
            self.destination_url = self.context.absolute_url()
            self.request.response.redirect(self.destination_url)
            return

        # Partition Preservation
        # the partition table shown in AR and Sample views sends it's
        # action button submits here.
        elif action == "preserve":
            objects = WorkflowAction._get_selected_items(self)
            transitioned = []
            for obj_uid, obj in objects.items():
                part = obj
                # can't transition inactive items
                if workflow.getInfoFor(part, 'inactive_state', '') == 'inactive':
                    continue
                if not checkPermission(PreserveSample, part):
                    continue

                # grab this object's Preserver and DatePreserved from the form
                Preserver = form['getPreserver'][0][obj_uid].strip()
                Preserver = Preserver and Preserver or ''
                DatePreserved = form['getDatePreserved'][0][obj_uid].strip()
                DatePreserved = DatePreserved and DateTime(DatePreserved) or ''

                # write them to the sample
                part.setPreserver(Preserver)
                part.setDatePreserved(DatePreserved)

                # transition the object if both values are present
                if Preserver and DatePreserved:
                    workflow.doActionFor(part, action)
                    transitioned.append(part.id)

                part.reindexObject()
                part.aq_parent.reindexObject()

            message = None
            if len(transitioned) > 1:
                message = _('${items} are waiting to be received.',
                            mapping={'items': ', '.join(transitioned)})
                message = self.context.translate(message)
                self.context.plone_utils.addPortalMessage(message, 'info')
            elif len(transitioned) == 1:
                message = _('${item} is waiting to be received.',
                            mapping={'item': ', '.join(transitioned)})
                message = self.context.translate(message)
                self.context.plone_utils.addPortalMessage(message, 'info')
            if not message:
                message = _('No changes made.')
                message = self.context.translate(message)
                self.context.plone_utils.addPortalMessage(message, 'info')
            self.destination_url = self.request.get_header("referer",
                                   self.context.absolute_url())
            self.request.response.redirect(self.destination_url)

        elif action == "sample":
            # This action happens only for a single context.
            # Context can be a sample or an AR.
            #
            # Once the Sampler/DateSampled values are completed on the
            # Sample or AR form, the user has two choices.
            #
            # 1) Use the normal Plone UI actions dropdown, (invokes this code).
            # 2) Click the save button, which invokes code in SampleEdit or
            #    AnalysisRequestEdit __call__ methods.
            #
            # Both these methods do pretty much the same thing, but now, it's
            # done in three places.

            if self.context.portal_type == "AnalysisRequest":
                sample = self.context.getSample()
            else:
                sample = self.context
            # can't transition inactive items
            if workflow.getInfoFor(sample, 'inactive_state', '') == 'inactive' \
               or not checkPermission(SampleSample, sample):
                message = _('No changes made.')
                message = self.context.translate(message)
                self.context.plone_utils.addPortalMessage(message, 'info')
                self.destination_url = self.request.get_header("referer",
                                       self.context.absolute_url())
                self.request.response.redirect(self.destination_url)
                return
            # grab this object's Sampler and DateSampled from the form
            Sampler = form['getSampler'][0][sample_uid].strip()
            Sampler = Sampler and Sampler or ''
            DateSampled = form['getDateSampled'][0][obj_uid].strip()
            DateSampled = DateSampled and DateTime(DateSampled) or ''
            # write them to the sample
            sample.setSampler(Sampler)
            sample.setDateSampled(DateSampled)
            # transition the object if both values are present
            if Sampler and DateSampled:
                workflow.doActionFor(sample, action)
                sample.reindexObject()
                message = "Changes saved."
                message = self.context.translate(message)
                self.context.plone_utils.addPortalMessage(message, 'info')
            self.destination_url = self.request.get_header("referer",
                                   self.context.absolute_url())
            self.request.response.redirect(self.destination_url)
            return

        elif action == "receive":
            # default bika_listing.py/WorkflowAction, but then
            # print automatic labels.
            if 'receive' in self.context.bika_setup.getAutoPrintLabels():
                size = self.context.bika_setup.getAutoLabelSize()
                q = "/sticker?size=%s&items=%s" % (size, self.context.getId())
                self.destination_url = self.context.absolute_url() + q
            WorkflowAction.__call__(self)

        # submit
        elif action == 'submit' and "Result" in self.request.form:
            if not isActive(self.context):
                message = self.context.translate(_('Item is inactive.'))
                self.context.plone_utils.addPortalMessage(message, 'info')
                self.request.response.redirect(self.context.absolute_url())
                return

            selected_analyses = WorkflowAction._get_selected_items(self)
            results = {}
            hasInterims = {}

            # check that the form values match the database
            # save them if not.
            for uid, result in self.request.form['Result'][0].items():
                # if the AR has ReportDryMatter set, get dry_result from form.
                dry_result = ''
                if hasattr(self.context, 'getReportDryMatter') \
                   and self.context.getReportDryMatter():
                    for k, v in self.request.form['ResultDM'][0].items():
                        if uid == k:
                            dry_result = v
                            break
                if uid in selected_analyses:
                    analysis = selected_analyses[uid]
                else:
                    analysis = rc.lookupObject(uid)
                if not analysis:
                    # ignore result if analysis object no longer exists
                    continue
                results[uid] = result
                service = analysis.getService()
                interimFields = item_data[uid]
                if len(interimFields) > 0:
                    hasInterims[uid] = True
                else:
                    hasInterims[uid] = False
                service_unit = service.getUnit() and service.getUnit() or ''
                retested = 'retested' in form and uid in form['retested']
                remarks = form.get('Remarks', [{}, ])[0].get(uid, '')
                # Don't save uneccessary things
                # https://github.com/bikalabs/Bika-LIMS/issues/766:
                #    Somehow, using analysis.edit() fails silently when
                #    logged in as Analyst.
                if analysis.getInterimFields() != interimFields or \
                   analysis.getRetested() != retested or \
                   analysis.getRemarks() != remarks:
                    analysis.setInterimFields(interimFields)
                    analysis.setRetested(retested)
                    analysis.setRemarks(remarks)
                # save results separately, otherwise capture date is rewritten
                if analysis.getResult() != result or \
                   analysis.getResultDM() != dry_result:
                    analysis.setResultDM(dry_result)
                    analysis.setResult(result)

            methods = self.request.form.get('Method', [{}])[0]
            instruments = self.request.form.get('Instrument', [{}])[0]
            analysts = self.request.form.get('Analyst', [{}])[0]

            # discover which items may be submitted
            submissable = []
            for uid, analysis in selected_analyses.items():

                analysis_active = isActive(analysis)

                # Need to save the method?
                if uid in methods and analysis_active:
                    # TODO: Add SetAnalysisMethod permission
                    # allow_setmethod = sm.checkPermission(SetAnalysisMethod)
                    allow_setmethod = True
                    # ---8<-----
                    if allow_setmethod == True and analysis.isMethodAllowed(methods[uid]):
                        analysis.setMethod(methods[uid])

                # Need to save the instrument?
                if uid in instruments and analysis_active:
                    # TODO: Add SetAnalysisInstrument permission
                    # allow_setinstrument = sm.checkPermission(SetAnalysisInstrument)
                    allow_setinstrument = True
                    # ---8<-----
                    if allow_setinstrument == True:
                        # The current analysis allows the instrument regards
                        # to its analysis service and method?
                        if analysis.isInstrumentAllowed(instruments[uid]):
                            previnstr = analysis.getInstrument()
                            if previnstr:
                                previnstr.removeAnalysis(analysis)
                            analysis.setInstrument(instruments[uid])
                            instrument = rc.lookupObject(instruments[uid])
                            instrument.addAnalysis(analysis)

                # Need to save the analyst?
                if uid in analysts and analysis_active:
                    analysis.setAnalyst(analysts[uid]);

                if uid not in results or not results[uid]:
                    continue
                can_submit = True
                # guard_submit does a lot of the same stuff, too.
                # the code there has also been commented.
                # we must find a better way to allow dependencies to control
                # this process.
                # for dependency in analysis.getDependencies():
                #     dep_state = workflow.getInfoFor(dependency, 'review_state')
                #     if hasInterims[uid]:
                #         if dep_state in ('to_be_sampled', 'to_be_preserved',
                #                          'sample_due', 'sample_received',
                #                          'attachment_due', 'to_be_verified',):
                #             can_submit = False
                #             break
                #     else:
                #         if dep_state in ('to_be_sampled', 'to_be_preserved',
                #                          'sample_due', 'sample_received',):
                #             can_submit = False
                #             break
                if can_submit and analysis not in submissable:
                    submissable.append(analysis)

            # and then submit them.
            for analysis in submissable:
                doActionFor(analysis, 'submit')

            message = self.context.translate(PMF("Changes saved."))
            self.context.plone_utils.addPortalMessage(message, 'info')
            if checkPermission(EditResults, self.context):
                self.destination_url = self.context.absolute_url() + "/manage_results"
            else:
                self.destination_url = self.context.absolute_url()
            self.request.response.redirect(self.destination_url)

        # publish
        elif action in ('prepublish', 'publish', 'republish'):
            if not isActive(self.context):
                message = self.context.translate(_('Item is inactive.'))
                self.context.plone_utils.addPortalMessage(message, 'info')
                self.request.response.redirect(self.context.absolute_url())
                return

            # publish entire AR.
            self.context.setDatePublished(DateTime())
            transitioned = self.doPublish(self.context,
                                   self.request,
                                   action,
                                   [self.context, ])()
            if len(transitioned) == 1:
                message = to_utf8(self.context.translate('${items} published.',
                                    mapping={'items': ', '.join(transitioned)}))
            else:
                message = self.context.translate(_("No items were published"))
            self.context.plone_utils.addPortalMessage(message, 'info')
            self.destination_url = self.request.get_header("referer",
                                   self.context.absolute_url())
            self.request.response.redirect(self.destination_url)

        # verify
        elif action == 'verify':
            # default bika_listing.py/WorkflowAction, but then go to view screen.
            self.destination_url = self.context.absolute_url()
            WorkflowAction.__call__(self)

        elif action == 'retract_ar':
            # AR should be retracted
            # Can't transition inactive ARs
            if not isActive(self.context):
                message = self.context.translate(_('Item is inactive.'))
                self.context.plone_utils.addPortalMessage(message, 'info')
                self.request.response.redirect(self.context.absolute_url())
                return

            # 1. Copies the AR linking the original one and viceversa
            ar = self.context
            newar = self.cloneAR(ar)

            # 2. The old AR gets a status of 'invalid'
            workflow.doActionFor(ar, 'retract_ar')

            # 3. The new AR copy opens in status 'to be verified'
            changeWorkflowState(newar, 'bika_ar_workflow', 'to_be_verified')

            # 4. The system immediately alerts the client contacts who ordered
            # the results, per email and SMS, that a possible mistake has been
            # picked up and is under investigation.
            # A much possible information is provided in the email, linking
            # to the AR online.
            laboratory = self.context.bika_setup.laboratory
            lab_address = "<br/>".join(laboratory.getPrintAddress())
            mime_msg = MIMEMultipart('related')
            mime_msg['Subject'] = _("Erroneus result publication from %s") % \
                                    ar.getRequestID()
            mime_msg['From'] = formataddr(
                (encode_header(laboratory.getName()),
                 laboratory.getEmailAddress()))
            to = []
            contact = ar.getContact()
            if contact:
                to.append(formataddr((encode_header(contact.Title()),
                                       contact.getEmailAddress())))
            for cc in ar.getCCContact():
                formatted = formataddr((encode_header(cc.Title()),
                                       cc.getEmailAddress()))
                if formatted not in to:
                    to.append(formatted)

            managers = self.context.portal_groups.getGroupMembers('LabManagers')
            for bcc in managers:
                user = self.portal.acl_users.getUser(bcc)
                uemail = user.getProperty('email')
                ufull = user.getProperty('fullname')
                formatted = formataddr((encode_header(ufull), uemail))
                if formatted not in to:
                    to.append(formatted)
            mime_msg['To'] = ','.join(to)
            aranchor = "<a href='%s'>%s</a>" % (ar.absolute_url(),
                                                ar.getRequestID())
            naranchor = "<a href='%s'>%s</a>" % (newar.absolute_url(),
                                                 newar.getRequestID())
            addremarks = ('addremarks' in self.request
                          and ar.getRemarks()) \
                        and ("<br/><br/>"
                             + _("Additional remarks:")
                             + "<br/>"
                             + ar.getRemarks().split("===")[1].strip()
                             + "<br/><br/>") \
                        or ''

            body = _("Some errors have been detected in the results report "
                     "published from the Analysis Request %s. The Analysis "
                     "Request %s has been created automatically and the "
                     "previous has been invalidated.<br/>The possible mistake "
                     "has been picked up and is under investigation.<br/><br/>"
                     "%s%s"
                     ) % (aranchor, naranchor, addremarks, lab_address)
            msg_txt = MIMEText(safe_unicode(body).encode('utf-8'),
                               _subtype='html')
            mime_msg.preamble = 'This is a multi-part MIME message.'
            mime_msg.attach(msg_txt)
            try:
                host = getToolByName(self.context, 'MailHost')
                host.send(mime_msg.as_string(), immediate=True)
            except Exception as msg:
                message = self.context.translate(
                        _('Unable to send an email to alert lab '
                          'client contacts that the Analysis Request has been '
                          'retracted: ${error}', mapping={'error': msg}))
                self.context.plone_utils.addPortalMessage(message, 'warning')

            message = self.context.translate('${items} invalidated.',
                                mapping={'items': ar.getRequestID()})
            self.context.plone_utils.addPortalMessage(message, 'warning')
            self.request.response.redirect(newar.absolute_url())

        else:
            # default bika_listing.py/WorkflowAction for other transitions
            WorkflowAction.__call__(self)

    def doPublish(self, context, request, action, analysis_requests):
        return doPublish(context, request, action, analysis_requests)

    def cloneAR(self, ar):
        _id = ar.aq_parent.invokeFactory('AnalysisRequest', id=tmpID())
        newar = ar.aq_parent[_id]
        newar.title = ar.title
        newar.description = ar.description
        RequestID = newar.getId()
        newar.setContact(ar.getContact())
        newar.setCCContact(ar.getCCContact())
        newar.setCCEmails(ar.getCCEmails())
        newar.setBatch(ar.getBatch())
        newar.setTemplate(ar.getTemplate())
        newar.setProfile(ar.getProfile())
        newar.setSamplingDate(ar.getSamplingDate())
        newar.setSampleType(ar.getSampleType())
        newar.setSamplePoint(ar.getSamplePoint())
        newar.setStorageLocation(ar.getStorageLocation())
        newar.setSamplingDeviation(ar.getSamplingDeviation())
        newar.setPriority(ar.getPriority())
        newar.setSampleCondition(ar.getSampleCondition())
        newar.setSample(ar.getSample())
        newar.setClientOrderNumber(ar.getClientOrderNumber())
        newar.setClientReference(ar.getClientReference())
        newar.setClientSampleID(ar.getClientSampleID())
        newar.setDefaultContainerType(ar.getDefaultContainerType())
        newar.setAdHoc(ar.getAdHoc())
        newar.setComposite(ar.getComposite())
        newar.setReportDryMatter(ar.getReportDryMatter())
        newar.setInvoiceExclude(ar.getInvoiceExclude())
        newar.setAttachment(ar.getAttachment())
        newar.setInvoice(ar.getInvoice())
        newar.setDateReceived(ar.getDateReceived())
        newar.setMemberDiscount(ar.getMemberDiscount())
        # Set the results for each AR analysis
        ans = ar.getAnalyses(full_objects=True)
        for an in ans:
            newar.invokeFactory("Analysis", id=an.getKeyword())
            nan = newar[an.getKeyword()]
            nan.setService(an.getService())
            nan.setCalculation(an.getCalculation())
            nan.setInterimFields(an.getInterimFields())
            nan.setResult(an.getResult())
            nan.setResultDM(an.getResultDM())
            nan.setRetested = False,
            nan.setMaxTimeAllowed(an.getMaxTimeAllowed())
            nan.setDueDate(an.getDueDate())
            nan.setDuration(an.getDuration())
            nan.setReportDryMatter(an.getReportDryMatter())
            nan.setAnalyst(an.getAnalyst())
            nan.setInstrument(an.getInstrument())
            nan.setSamplePartition(an.getSamplePartition())
            nan.unmarkCreationFlag()
            zope.event.notify(ObjectInitializedEvent(nan))
            changeWorkflowState(nan, 'bika_analysis_workflow',
                                'to_be_verified')
            nan.reindexObject()

        newar.reindexObject()
        newar.aq_parent.reindexObject()
        renameAfterCreation(newar)
        newar.setRequestID(newar.getId())

        if hasattr(ar, 'setChildAnalysisRequest'):
            ar.setChildAnalysisRequest(newar)
        newar.setParentAnalysisRequest(ar)
        return newar