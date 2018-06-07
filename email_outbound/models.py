# email_outbound/models.py
# Brought to you by We Vote. Be good.
# -*- coding: UTF-8 -*-

from django.core.mail import EmailMultiAlternatives
from django.db import models
from wevote_functions.functions import extract_email_addresses_from_string, generate_random_string, \
    positive_value_exists
from wevote_settings.models import fetch_next_we_vote_id_email_integer, fetch_site_unique_id_prefix

FRIEND_ACCEPTED_INVITATION_TEMPLATE = 'FRIEND_ACCEPTED_INVITATION_TEMPLATE'
FRIEND_INVITATION_TEMPLATE = 'FRIEND_INVITATION_TEMPLATE'
GENERIC_EMAIL_TEMPLATE = 'GENERIC_EMAIL_TEMPLATE'
LINK_TO_SIGN_IN_TEMPLATE = 'LINK_TO_SIGN_IN_TEMPLATE'
VERIFY_EMAIL_ADDRESS_TEMPLATE = 'VERIFY_EMAIL_ADDRESS_TEMPLATE'
SEND_BALLOT_TO_SELF = 'SEND_BALLOT_TO_SELF'
SEND_BALLOT_TO_FRIENDS = 'SEND_BALLOT_TO_FRIENDS'
KIND_OF_EMAIL_TEMPLATE_CHOICES = (
    (GENERIC_EMAIL_TEMPLATE,  'Generic Email'),
    (FRIEND_ACCEPTED_INVITATION_TEMPLATE, 'Accept an invitation to be a Friend'),
    (FRIEND_INVITATION_TEMPLATE, 'Invite Friend'),
    (LINK_TO_SIGN_IN_TEMPLATE, 'Link to sign in.'),
    (VERIFY_EMAIL_ADDRESS_TEMPLATE, 'Verify Senders Email Address'),
    (SEND_BALLOT_TO_SELF, 'Send ballot to self'),
    (SEND_BALLOT_TO_FRIENDS, 'Send ballot to friends'),
)

TO_BE_PROCESSED = 'TO_BE_PROCESSED'
BEING_ASSEMBLED = 'BEING_ASSEMBLED'
SCHEDULED = 'SCHEDULED'
ASSEMBLY_STATUS_CHOICES = (
    (TO_BE_PROCESSED,  'Email to be assembled'),
    (BEING_ASSEMBLED, 'Email being assembled with template'),
    (SCHEDULED, 'Sent to the scheduler'),
)
WAITING_FOR_VERIFICATION = 'WAITING_FOR_VERIFICATION'

BEING_SENT = 'BEING_SENT'
SENT = 'SENT'
SEND_STATUS_CHOICES = (
    (TO_BE_PROCESSED,  'Message to be processed'),
    (BEING_SENT, 'Message being sent'),
    (SENT, 'Message sent'),
)


class EmailAddress(models.Model):
    """
    We give every email address its own unique we_vote_id for things like invitations
    """
    # The we_vote_id identifier is unique across all We Vote sites, and allows us to share our data with other
    # organizations
    # It starts with "wv" then we add on a database specific identifier like "3v" (WeVoteSetting.site_unique_id_prefix)
    # then the string "email", and then a sequential integer like "123".
    # We keep the last value in WeVoteSetting.we_vote_id_last_email_integer
    we_vote_id = models.CharField(
        verbose_name="we vote id of this email address", max_length=255, default=None, null=True,
        blank=True, unique=True)
    voter_we_vote_id = models.CharField(
        verbose_name="we vote id for the email owner", max_length=255, null=True, blank=True, unique=False)
    # Until an EmailAddress has had its ownership verified, multiple voter accounts can try to use it
    normalized_email_address = models.EmailField(
        verbose_name='email address', max_length=255, null=False, blank=False, unique=False)
    # Has this email been verified by the owner?
    email_ownership_is_verified = models.BooleanField(default=False)
    # Has this email had a permanent bounce? If so, we should not send emails to it.
    email_permanent_bounce = models.BooleanField(default=False)
    secret_key = models.CharField(
        verbose_name="secret key to verify ownership of email", max_length=255, null=True, blank=True, unique=True)
    deleted = models.BooleanField(default=False)  # If email address is removed from person's account, mark as deleted

    # We override the save function so we can auto-generate we_vote_id
    def save(self, *args, **kwargs):
        # Even if this data came from another source we still need a unique we_vote_id
        if self.we_vote_id:
            self.we_vote_id = self.we_vote_id.strip().lower()
        if self.we_vote_id == "" or self.we_vote_id is None:  # If there isn't a value...
            # ...generate a new id
            site_unique_id_prefix = fetch_site_unique_id_prefix()
            next_local_integer = fetch_next_we_vote_id_email_integer()
            # "wv" = We Vote
            # site_unique_id_prefix = a generated (or assigned) unique id for one server running We Vote
            # "email" = tells us this is a unique id for a EmailAddress
            # next_integer = a unique, sequential integer for this server - not necessarily tied to database id
            self.we_vote_id = "wv{site_unique_id_prefix}email{next_integer}".format(
                site_unique_id_prefix=site_unique_id_prefix,
                next_integer=next_local_integer,
            )
        super(EmailAddress, self).save(*args, **kwargs)


class EmailOutboundDescription(models.Model):
    """
    Specifications for a single email we want to send. This data is used to assemble an EmailScheduled
    """
    kind_of_email_template = models.CharField(max_length=50, choices=KIND_OF_EMAIL_TEMPLATE_CHOICES,
                                              default=GENERIC_EMAIL_TEMPLATE)
    sender_voter_we_vote_id = models.CharField(
        verbose_name="we vote id for the sender", max_length=255, null=True, blank=True, unique=False)
    sender_voter_email = models.EmailField(
        verbose_name='email address for sender', max_length=255, null=True, blank=True, unique=False)
    recipient_voter_we_vote_id = models.CharField(
        verbose_name="we vote id for the recipient if we have it", max_length=255, null=True, blank=True, unique=False)
    recipient_email_we_vote_id = models.CharField(
        verbose_name="email we vote id for recipient", max_length=255, null=True, blank=True, unique=False)
    # We include this here for data monitoring and debugging
    recipient_voter_email = models.EmailField(
        verbose_name='email address for recipient', max_length=255, null=True, blank=True, unique=False)
    template_variables_in_json = models.TextField(null=True, blank=True)
    date_last_changed = models.DateTimeField(verbose_name='date last changed', null=True, auto_now=True)


class EmailScheduled(models.Model):
    """
    Used to tell the email server literally what to send. If an email bounces temporarily, we will
    want to trigger the EmailOutboundDescription to generate an new EmailScheduled entry.
    """
    subject = models.CharField(verbose_name="email subject", max_length=255, null=True, blank=True, unique=False)
    message_text = models.TextField(null=True, blank=True)
    message_html = models.TextField(null=True, blank=True)
    sender_voter_we_vote_id = models.CharField(
        verbose_name="we vote id for the sender", max_length=255, null=True, blank=True, unique=False)
    sender_voter_email = models.EmailField(
        verbose_name='sender email address', max_length=255, null=True, blank=True, unique=False)
    recipient_voter_we_vote_id = models.CharField(
        verbose_name="we vote id for the recipient", max_length=255, null=True, blank=True, unique=False)
    recipient_email_we_vote_id = models.CharField(
        verbose_name="we vote id for the email", max_length=255, null=True, blank=True, unique=False)
    recipient_voter_email = models.EmailField(
        verbose_name='recipient email address', max_length=255, null=True, blank=True, unique=False)
    send_status = models.CharField(max_length=50, choices=SEND_STATUS_CHOICES, default=TO_BE_PROCESSED)
    email_outbound_description_id = models.PositiveIntegerField(
        verbose_name="the internal id of EmailOutboundDescription", default=0, null=False)
    date_last_changed = models.DateTimeField(verbose_name='date last changed', null=True, auto_now=True)


class EmailManager(models.Model):
    def __unicode__(self):
        return "EmailManager"

    def create_email_address_for_voter(self, normalized_email_address, voter, email_ownership_is_verified=False):
        return self.create_email_address(normalized_email_address, voter.we_vote_id, email_ownership_is_verified)

    def create_email_address(self, normalized_email_address, voter_we_vote_id='', email_ownership_is_verified=False,
                             make_primary_email=True):
        secret_key = generate_random_string(12)
        normalized_email_address = str(normalized_email_address)
        normalized_email_address = normalized_email_address.strip()
        normalized_email_address = normalized_email_address.lower()

        if not positive_value_exists(normalized_email_address):
            email_address_object = EmailAddress()
            results = {
                'success':                      False,
                'status':                       "EMAIL_ADDRESS_FOR_VOTER_MISSING_RAW_EMAIL",
                'email_address_object_saved':   False,
                'email_address_object':         email_address_object,
            }
            return results

        try:
            email_address_object = EmailAddress.objects.create(
                normalized_email_address=normalized_email_address,
                voter_we_vote_id=voter_we_vote_id,
                email_ownership_is_verified=email_ownership_is_verified,
                secret_key=secret_key,
            )
            email_address_object_saved = True
            success = True
            status = "EMAIL_ADDRESS_FOR_VOTER_CREATED"
        except Exception as e:
            email_address_object_saved = False
            email_address_object = EmailAddress()
            success = False
            status = "EMAIL_ADDRESS_FOR_VOTER_NOT_CREATED"

        results = {
            'success':                    success,
            'status':                     status,
            'email_address_object_saved': email_address_object_saved,
            'email_address_object':       email_address_object,
        }
        return results

    def create_email_outbound_description(
            self, sender_voter_we_vote_id, sender_voter_email,
            recipient_voter_we_vote_id='',
            recipient_email_we_vote_id='', recipient_voter_email='', template_variables_in_json='',
            kind_of_email_template=''):
        if not positive_value_exists(kind_of_email_template):
            kind_of_email_template = GENERIC_EMAIL_TEMPLATE

        try:
            email_outbound_description = EmailOutboundDescription.objects.create(
                sender_voter_we_vote_id=sender_voter_we_vote_id,
                sender_voter_email=sender_voter_email,
                recipient_voter_we_vote_id=recipient_voter_we_vote_id,
                recipient_email_we_vote_id=recipient_email_we_vote_id,
                recipient_voter_email=recipient_voter_email,
                kind_of_email_template=kind_of_email_template,
                template_variables_in_json=template_variables_in_json,
            )
            email_outbound_description_saved = True
            success = True
            status = "EMAIL_OUTBOUND_DESCRIPTION_CREATED"
        except Exception as e:
            email_outbound_description_saved = False
            email_outbound_description = EmailOutboundDescription()
            success = False
            status = "EMAIL_OUTBOUND_DESCRIPTION_NOT_CREATED"

        results = {
            'success':                          success,
            'status':                           status,
            'email_outbound_description_saved': email_outbound_description_saved,
            'email_outbound_description':       email_outbound_description,
        }
        return results

    def parse_raw_emails_into_list(self, email_addresses_raw):
        success = True
        status = "EMAIL_MANAGER_PARSE_RAW_EMAILS"
        email_list = extract_email_addresses_from_string(email_addresses_raw)

        results = {
            'success':                  success,
            'status':                   status,
            'at_least_one_email_found': True,
            'email_list':               email_list,
        }
        return results

    def retrieve_email_address_object(self, normalized_email_address, email_address_object_we_vote_id='',
                                      voter_we_vote_id=''):
        """
        There are cases where we store multiple entries for the same normalized_email_address (prior to an email
        address being verified)
        :param normalized_email_address:
        :param email_address_object_we_vote_id:
        :param voter_we_vote_id:
        :return:
        """
        exception_does_not_exist = False
        exception_multiple_object_returned = False
        email_address_object_found = False
        email_address_object = EmailAddress()
        email_address_object_id = 0
        email_address_list_found = False
        email_address_list = []
        status = ""

        try:
            if positive_value_exists(email_address_object_we_vote_id):
                if positive_value_exists(voter_we_vote_id):
                    email_address_object = EmailAddress.objects.get(
                        we_vote_id__iexact=email_address_object_we_vote_id,
                        voter_we_vote_id__iexact=voter_we_vote_id,
                        deleted=False
                    )
                else:
                    email_address_object = EmailAddress.objects.get(
                        we_vote_id__iexact=email_address_object_we_vote_id,
                        deleted=False
                    )
                email_address_object_id = email_address_object.id
                email_address_object_we_vote_id = email_address_object.we_vote_id
                email_address_object_found = True
                success = True
                status += "RETRIEVE_EMAIL_ADDRESS_FOUND_BY_WE_VOTE_ID "
            elif positive_value_exists(normalized_email_address):
                email_address_queryset = EmailAddress.objects.all()
                if positive_value_exists(voter_we_vote_id):
                    email_address_queryset = email_address_queryset.filter(
                        normalized_email_address__iexact=normalized_email_address,
                        voter_we_vote_id__iexact=voter_we_vote_id,
                        deleted=False
                    )
                else:
                    email_address_queryset = email_address_queryset.filter(
                        normalized_email_address__iexact=normalized_email_address,
                        deleted=False
                    )
                # We need the email that has been verified email at top of list
                email_address_queryset = email_address_queryset.order_by('-email_ownership_is_verified')
                email_address_list = email_address_queryset

                if len(email_address_list):
                    if len(email_address_list) == 1:
                        # If only one email is found, return the results as a single email
                        email_address_object = email_address_list[0]
                        email_address_object_id = email_address_object.id
                        email_address_object_we_vote_id = email_address_object.we_vote_id
                        email_address_object_found = True
                        email_address_list_found = False
                        success = True
                        status += "RETRIEVE_EMAIL_ADDRESS_FOUND_BY_NORMALIZED_EMAIL_ADDRESS "
                    else:
                        success = True
                        email_address_list_found = True
                        status += 'RETRIEVE_EMAIL_ADDRESS_OBJECT-EMAIL_ADDRESS_LIST_RETRIEVED '
                else:
                    success = True
                    email_address_list_found = False
                    status += 'RETRIEVE_EMAIL_ADDRESS_OBJECT-NO_EMAIL_ADDRESS_LIST_RETRIEVED '
            else:
                email_address_object_found = False
                success = False
                status += "RETRIEVE_EMAIL_ADDRESS_VARIABLES_MISSING "
        except EmailAddress.DoesNotExist:
            exception_does_not_exist = True
            success = True
            status += "RETRIEVE_EMAIL_ADDRESS_NOT_FOUND "
        except Exception as e:
            success = False
            status += 'FAILED retrieve_email_address_object EmailAddress'

        results = {
            'success':                          success,
            'status':                           status,
            'DoesNotExist':                     exception_does_not_exist,
            'MultipleObjectsReturned':          exception_multiple_object_returned,
            'email_address_object_found':       email_address_object_found,
            'email_address_object_id':          email_address_object_id,
            'email_address_object_we_vote_id':  email_address_object_we_vote_id,
            'email_address_object':             email_address_object,
            'email_address_list_found':         email_address_list_found,
            'email_address_list':               email_address_list,
        }
        return results

    def retrieve_email_address_object_from_secret_key(self, email_secret_key):
        """
        :param email_secret_key:
        :return:
        """
        email_address_object_found = False
        email_address_object = EmailAddress()
        email_address_object_id = 0
        email_address_object_we_vote_id = ""

        try:
            if positive_value_exists(email_secret_key):
                email_address_object = EmailAddress.objects.get(
                    secret_key=email_secret_key,
                )
                email_address_object_id = email_address_object.id
                email_address_object_we_vote_id = email_address_object.we_vote_id
                email_address_object_found = True
                success = True
                status = "RETRIEVE_EMAIL_ADDRESS_FOUND_BY_SECRET_KEY"
            else:
                email_address_object_found = False
                success = False
                status = "RETRIEVE_EMAIL_ADDRESS_BY_SECRET_KEY_VARIABLES_MISSING"
        except EmailAddress.DoesNotExist:
            success = True
            status = "RETRIEVE_EMAIL_ADDRESS_BY_SECRET_KEY_NOT_FOUND"
        except Exception as e:
            success = False
            status = 'FAILED retrieve_email_address_object_from_secret_key EmailAddress'

        results = {
            'success':                          success,
            'status':                           status,
            'email_address_object_found':       email_address_object_found,
            'email_address_object_id':          email_address_object_id,
            'email_address_object_we_vote_id':  email_address_object_we_vote_id,
            'email_address_object':             email_address_object,
        }
        return results

    def email_address_sign_in_from_secret_key(self, email_secret_key):
        """
        :param email_secret_key:
        :return:
        """
        email_address_object_found = False
        email_address_object = EmailAddress()
        email_address_object_id = 0
        email_address_object_we_vote_id = ""
        email_ownership_is_verified = False

        try:
            if positive_value_exists(email_secret_key):
                email_address_object = EmailAddress.objects.get(
                    secret_key=email_secret_key,
                    deleted=False
                )
                email_address_object_id = email_address_object.id
                email_address_object_we_vote_id = email_address_object.we_vote_id
                email_ownership_is_verified = email_address_object.email_ownership_is_verified
                email_address_object_found = True
                success = True
                status = "EMAIL_ADDRESS_SIGN_IN_BY_WE_VOTE_ID"
            else:
                email_address_object_found = False
                success = False
                status = "EMAIL_ADDRESS_SIGN_IN_VARIABLES_MISSING"
        except EmailAddress.DoesNotExist:
            success = True
            status = "EMAIL_ADDRESS_SIGN_IN_NOT_FOUND"
        except Exception as e:
            success = False
            status = 'FAILED email_address_sign_in_from_secret_key EmailAddress'

        results = {
            'success':                          success,
            'status':                           status,
            'email_address_object_found':       email_address_object_found,
            'email_address_object_id':          email_address_object_id,
            'email_address_object_we_vote_id':  email_address_object_we_vote_id,
            'email_address_object':             email_address_object,
            'email_ownership_is_verified':      email_ownership_is_verified,
        }
        return results

    def verify_email_address_object_from_secret_key(self, email_secret_key):
        """

        :param email_secret_key:
        :return:
        """
        email_address_object_found = False
        email_address_object = EmailAddress()
        email_address_object_id = 0
        email_address_object_we_vote_id = ""

        try:
            if positive_value_exists(email_secret_key):
                email_address_object = EmailAddress.objects.get(
                    secret_key=email_secret_key,
                    email_ownership_is_verified=False,
                    deleted=False
                )
                email_address_object_id = email_address_object.id
                email_address_object_we_vote_id = email_address_object.we_vote_id
                email_address_object_found = True
                success = True
                status = "VERIFY_EMAIL_ADDRESS_FOUND_BY_WE_VOTE_ID"
            else:
                email_address_object_found = False
                success = False
                status = "VERIFY_EMAIL_ADDRESS_VARIABLES_MISSING"
        except EmailAddress.DoesNotExist:
            success = True
            status = "VERIFY_EMAIL_ADDRESS_NOT_FOUND"
        except Exception as e:
            success = False
            status = 'FAILED verify_email_address_object_from_secret_key EmailAddress'

        email_ownership_is_verified = False
        if email_address_object_found:
            try:
                # Note that we leave the secret key in place so we can the owner we_vote_id in a subsequent call
                email_address_object.email_ownership_is_verified = True
                email_address_object.save()
                email_ownership_is_verified = True
            except Exception as e:
                success = False
                status = 'FAILED_TO_SAVE_EMAIL_OWNERSHIP_IS_VERIFIED'

        results = {
            'success':                          success,
            'status':                           status,
            'email_address_object_found':       email_address_object_found,
            'email_address_object_id':          email_address_object_id,
            'email_address_object_we_vote_id':  email_address_object_we_vote_id,
            'email_address_object':             email_address_object,
            'email_ownership_is_verified':      email_ownership_is_verified,
        }
        return results

    def retrieve_voter_email_address_list(self, voter_we_vote_id):
        """

        :param voter_we_vote_id:
        :return:
        """
        status = ""
        if not positive_value_exists(voter_we_vote_id):
            success = False
            status += 'VALID_VOTER_WE_VOTE_ID_MISSING '
            results = {
                'success':                  success,
                'status':                   status,
                'voter_we_vote_id':         voter_we_vote_id,
                'email_address_list_found': False,
                'email_address_list':       [],
            }
            return results

        email_address_list = []
        try:
            email_address_queryset = EmailAddress.objects.all()
            email_address_queryset = email_address_queryset.filter(
                voter_we_vote_id__iexact=voter_we_vote_id,
                deleted=False
            )
            email_address_queryset = email_address_queryset.order_by('-id')  # Put most recent email at top of list
            email_address_list = email_address_queryset

            if len(email_address_list):
                success = True
                email_address_list_found = True
                status += 'EMAIL_ADDRESS_LIST_RETRIEVED '
            else:
                success = True
                email_address_list_found = False
                status += 'NO_EMAIL_ADDRESS_LIST_RETRIEVED '
        except EmailAddress.DoesNotExist:
            # No data found. Not a problem.
            success = True
            email_address_list_found = False
            status += 'NO_EMAIL_ADDRESS_LIST_RETRIEVED_DoesNotExist '
            email_address_list = []
        except Exception as e:
            success = False
            email_address_list_found = False
            status += 'FAILED retrieve_voter_email_address_list EmailAddress '

        results = {
            'success': success,
            'status': status,
            'voter_we_vote_id': voter_we_vote_id,
            'email_address_list_found': email_address_list_found,
            'email_address_list': email_address_list,
        }
        return results

    def retrieve_primary_email_with_ownership_verified(self, voter_we_vote_id, normalized_email_address=''):
        email_address_list = []
        email_address_list_found = False
        email_address_object = EmailAddress()
        email_address_object_found = False
        try:
            if positive_value_exists(voter_we_vote_id):
                email_address_queryset = EmailAddress.objects.all()
                email_address_queryset = email_address_queryset.filter(
                    voter_we_vote_id__iexact=voter_we_vote_id,
                    email_ownership_is_verified=True,
                    deleted=False
                )
                email_address_queryset = email_address_queryset.order_by('-id')  # Put most recent email at top of list
                email_address_list = email_address_queryset
            elif positive_value_exists(normalized_email_address):
                email_address_queryset = EmailAddress.objects.all()
                email_address_queryset = email_address_queryset.filter(
                    normalized_email_address__iexact=normalized_email_address,
                    email_ownership_is_verified=True,
                    deleted=False
                )
                email_address_queryset = email_address_queryset.order_by('-id')  # Put most recent email at top of list
                email_address_list = email_address_queryset
            else:
                email_address_list = []
            if len(email_address_list):
                success = True
                email_address_list_found = True
                status = 'RETRIEVE_PRIMARY_EMAIL_ADDRESS_OBJECT-EMAIL_ADDRESS_LIST_RETRIEVED'
            else:
                success = True
                email_address_list_found = False
                status = 'RETRIEVE_PRIMARY_EMAIL_ADDRESS_OBJECT-NO_EMAIL_ADDRESS_LIST_RETRIEVED'
        except EmailAddress.DoesNotExist:
            success = True
            status = "RETRIEVE_PRIMARY_EMAIL_ADDRESS_NOT_FOUND"
        except Exception as e:
            success = False
            status = 'FAILED retrieve_primary_email_with_ownership_verified EmailAddress'

        if email_address_list_found:
            email_address_object_found = True
            email_address_object = email_address_list[0]

        results = {
            'success':                          success,
            'status':                           status,
            'email_address_object_found':       email_address_object_found,
            'email_address_object':             email_address_object,
        }
        return results

    def fetch_primary_email_with_ownership_verified(self, voter_we_vote_id):
        results = self.retrieve_primary_email_with_ownership_verified(voter_we_vote_id)
        if results['email_address_object_found']:
            email_address_object = results['email_address_object']
            return email_address_object.normalized_email_address

        return ""

    def retrieve_scheduled_email_list_from_send_status(self, sender_voter_we_vote_id, send_status):
        scheduled_email_list = []
        try:
            email_scheduled_queryset = EmailScheduled.objects.all()
            email_scheduled_queryset = email_scheduled_queryset.filter(
                sender_voter_we_vote_id=sender_voter_we_vote_id,
                send_status=send_status,
            )
            scheduled_email_list = email_scheduled_queryset

            if len(scheduled_email_list):
                success = True
                scheduled_email_list_found = True
                status = 'SCHEDULED_EMAIL_LIST_RETRIEVED'
            else:
                success = True
                scheduled_email_list_found = False
                status = 'NO_SCHEDULED_EMAIL_LIST_RETRIEVED'
        except EmailScheduled.DoesNotExist:
            # No data found. Not a problem.
            success = True
            scheduled_email_list_found = False
            status = 'NO_SCHEDULED_EMAIL_LIST_RETRIEVED_DoesNotExist'
            scheduled_email_list = []
        except Exception as e:
            success = False
            scheduled_email_list_found = False
            status = 'FAILED retrieve_scheduled_email_list_from_send_status EmailAddress'

        results = {
            'success':                      success,
            'status':                       status,
            'scheduled_email_list_found':   scheduled_email_list_found,
            'scheduled_email_list':         scheduled_email_list,
        }
        return results

    def update_scheduled_email_with_new_send_status(self, email_scheduled_object, send_status):
        try:
            email_scheduled_object.send_status = send_status
            email_scheduled_object.save()
            return email_scheduled_object
        except Exception as e:
            return email_scheduled_object

    def schedule_email(self, email_outbound_description, subject, message_text, message_html,
                       send_status=TO_BE_PROCESSED):
        try:
            email_scheduled = EmailScheduled.objects.create(
                sender_voter_we_vote_id=email_outbound_description.sender_voter_we_vote_id,
                sender_voter_email=email_outbound_description.sender_voter_email,
                recipient_voter_we_vote_id=email_outbound_description.recipient_voter_we_vote_id,
                recipient_email_we_vote_id=email_outbound_description.recipient_email_we_vote_id,
                recipient_voter_email=email_outbound_description.recipient_voter_email,
                message_html=message_html,
                message_text=message_text,
                email_outbound_description_id=email_outbound_description.id,
                send_status=send_status,
                subject=subject,
            )
            email_scheduled_saved = True
            email_scheduled_id = email_scheduled.id
            success = True
            status = "SCHEDULE_EMAIL_CREATED"
        except Exception as e:
            email_scheduled_saved = False
            email_scheduled = EmailScheduled()
            email_scheduled_id = 0
            success = False
            status = "SCHEDULE_EMAIL_NOT_CREATED"

        results = {
            'success':                  success,
            'status':                   status,
            'email_scheduled_saved':    email_scheduled_saved,
            'email_scheduled_id':       email_scheduled_id,
            'email_scheduled':          email_scheduled,
        }
        return results

    def send_scheduled_email(self, email_scheduled):
        success = True
        status = ""

        # DALE 2016-11-3 sender_voter_email is no longer required, because we use a system email
        # if not positive_value_exists(email_scheduled.sender_voter_email):
        #     status += "MISSING_SENDER_VOTER_EMAIL"
        #     success = False

        if not positive_value_exists(email_scheduled.recipient_voter_email):
            status += "MISSING_RECIPIENT_VOTER_EMAIL"
            success = False

        if not positive_value_exists(email_scheduled.subject):
            status += "MISSING_EMAIL_SUBJECT "
            success = False

        # We need either plain text or HTML message
        if not positive_value_exists(email_scheduled.message_text) and \
                not positive_value_exists(email_scheduled.message_html):
            status += "MISSING_EMAIL_MESSAGE "
            success = False

        if success:
            return self.send_scheduled_email_via_sendgrid(email_scheduled)
        else:
            email_scheduled_sent = False
            results = {
                'success': success,
                'status': status,
                'email_scheduled_sent': email_scheduled_sent,
            }
            return results

    def send_scheduled_email_via_sendgrid(self, email_scheduled):
        """
        Send a single scheduled email
        :param email_scheduled:
        :return:
        """
        status = ""
        success = True
        sendgrid_turned_off_for_testing = False
        if sendgrid_turned_off_for_testing:
            status = "SENDGRID_TURNED_OFF_FOR_TESTING "
            results = {
                'success':                  success,
                'status':                   status,
                'email_scheduled_sent':     True,
            }
            return results

        system_sender_email_address = "We Vote <info@WeVote.US>"  # TODO DALE Make system variable

        mail = EmailMultiAlternatives(
            subject=email_scheduled.subject,
            body=email_scheduled.message_text,
            from_email=system_sender_email_address,
            to=[email_scheduled.recipient_voter_email],
            headers={"Reply-To": email_scheduled.sender_voter_email}
        )
        # TODO DALE ADD: reply_to = email_scheduled.sender_voter_email,
        if positive_value_exists(email_scheduled.message_html):
            mail.attach_alternative(email_scheduled.message_html, "text/html")

        try:
            mail.send()
            status += "SENDING_VIA_SENDGRID "
        except Exception as e:
            status += "COULD_NOT_SEND_VIA_SENDGRID "

        email_scheduled_sent = True

        results = {
            'success':                  success,
            'status':                   status,
            'email_scheduled_sent':     email_scheduled_sent,
        }
        return results

    def send_scheduled_email_list(self, messages_to_send):
        """
        Take in a list of scheduled_email_id's, and send them
        :param messages_to_send:
        :return:
        """
        success = False
        status = ""

        results = {
            'success':                  success,
            'status':                   status,
            'at_least_one_email_found': True,
        }
        return results

    def update_email_address_with_new_secret_key(self, email_we_vote_id):
        results = self.retrieve_email_address_object('', email_we_vote_id)
        if results['email_address_object_found']:
            email_address_object = results['email_address_object']
            try:
                email_address_object.secret_key = generate_random_string(12)
                email_address_object.save()
                return email_address_object.secret_key
            except Exception as e:
                return ""
        else:
            return ""

    def update_email_address_object_as_verified(self, email_address_object):
        try:
            email_address_object.email_ownership_is_verified = True
            email_address_object.save()
            return email_address_object
        except Exception as e:
            return email_address_object
