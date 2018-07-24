# import_export_facebook/views_admin.py
# Brought to you by We Vote. Be good.
# -*- coding: UTF-8 -*-

from .controllers import scrape_facebook_photo_url_from_web_page
from admin_tools.views import redirect_to_sign_in_page
from candidate.controllers import FACEBOOK, save_image_to_candidate_table
from candidate.models import CandidateCampaign
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from voter.models import voter_has_authority
from wevote_functions.functions import convert_to_int, positive_value_exists
import wevote_functions.admin
from wevote_settings.models import RemoteRequestHistory, RemoteRequestHistoryManager, RETRIEVE_POSSIBLE_FACEBOOK_PHOTOS


logger = wevote_functions.admin.get_logger(__name__)


def scrape_one_facebook_page(one_candidate, request, remote_request_history_manager, add_messages):
    # Facebook profile image url scrape has not been run on this candidate yet
    results = scrape_facebook_photo_url_from_web_page(one_candidate.facebook_url)
    if results.get('success'):
        photo_url = results.get('photo_url')
        link_is_broken = results.get('http_response_code') == 404
        if not photo_url.startswith('https://scontent') and not link_is_broken:
            logger.info("Rejected URL: " + one_candidate.facebook_url + " X '" + photo_url + "'")
            if add_messages:
                messages.add_message(request, messages.ERROR, 'Facebook photo NOT retrieved.')
        else:
            if link_is_broken:
                logger.info("Broken URL: " + one_candidate.facebook_url)
            else:
                logger.info("Scraped URL: " + one_candidate.facebook_url + " ==> " + photo_url)
            save_image_to_candidate_table(one_candidate, photo_url, one_candidate.facebook_url, link_is_broken,
                                          FACEBOOK)
            if add_messages:
                messages.add_message(request, messages.INFO, 'Facebook photo retrieved.')
        # Create a record denoting that we have retrieved from Facebook for this candidate
        save_results_history = remote_request_history_manager.create_remote_request_history_entry(
            RETRIEVE_POSSIBLE_FACEBOOK_PHOTOS, one_candidate.google_civic_election_id,
            one_candidate.we_vote_id, None, 1, "CANDIDATE_FACEBOOK_URL_PARSED_HTTP:" +
                                               str(link_is_broken) + ", " + one_candidate.facebook_url)
    elif add_messages:
        messages.add_message(request, messages.ERROR, 'Facebook photo NOT retrieved (2).')



# Test SQL for pgAdmin 4
# Find all eligible rows
#   SELECT * FROM public.candidate_candidatecampaign
#     where google_civic_election_id = '4456' and facebook_profile_image_url_https is null and
#     (facebook_url is not null or facebook_url != '');
# Set all the facebook facebook_profile_image_url_https picture urls to null
#   UPDATE public.candidate_candidatecampaign SET facebook_profile_image_url_https = NULL;
# Set all the  all the facebook_urls that are '' to null
#   UPDATE public.candidate_candidatecampaign SET facebook_url = NULL where facebook_url = '';
# Count all the facebook_profile_image_url_https picture urls
#   SELECT COUNT(facebook_profile_image_url_https) FROM public.candidate_candidatecampaign;
# Count how many facebook_urls exist
#   SELECT COUNT(facebook_url) FROM public.candidate_candidatecampaign;
# Get all the lines for a specific google_civic_election_id
#   SELECT * FROM public.candidate_candidatecampaign where google_civic_election_id = '1000052';
# Ignoring remote_request_history_manager, how many facebook_urls are there to process?
#   SELECT COUNT(facebook_url) FROM public.candidate_candidatecampaign where
# facebook_profile_image_url_https is null and google_civic_election_id = '1000052'; … 17
# Clear the wevote_settings_remoterequesthistory table to allow all lines to be processed, by right clicking
# on the table in pgAdmin and choosing truncate


@login_required
def bulk_retrieve_facebook_photos_view(request):
    remote_request_history_manager = RemoteRequestHistoryManager()

    authority_required = {'verified_volunteer'}  # admin, verified_volunteer
    if not voter_has_authority(request, authority_required):
        return redirect_to_sign_in_page(request, authority_required)

    google_civic_election_id = convert_to_int(request.GET.get('google_civic_election_id', 0))
    hide_candidate_tools = request.GET.get('hide_candidate_tools', False)
    page = request.GET.get('page', 0)
    state_code = request.GET.get('state_code', '')
    limit = convert_to_int(request.GET.get('show_all', 0))

    if not positive_value_exists(google_civic_election_id) and not positive_value_exists(state_code) \
            and not positive_value_exists(limit):
        messages.add_message(request, messages.ERROR,
                             'bulk_retrieve_facebook_photos_view, LIMITING_VARIABLE_REQUIRED')
        return HttpResponseRedirect(reverse('candidate:candidate_list', args=()) +
                                    '?google_civic_election_id=' + str(google_civic_election_id) +
                                    '&state_code=' + str(state_code) +
                                    '&hide_candidate_tools=' + str(hide_candidate_tools) +
                                    '&page=' + str(page)
                                    )

    try:
        candidate_list = CandidateCampaign.objects.all()
        if positive_value_exists(google_civic_election_id):
            candidate_list = candidate_list.filter(google_civic_election_id=google_civic_election_id)
        if positive_value_exists(state_code):
            candidate_list = candidate_list.filter(state_code__iexact=state_code)
        candidate_list = candidate_list.order_by('candidate_name')
        if positive_value_exists(limit):
            candidate_list = candidate_list[:limit]
        candidate_list_count = candidate_list.count()

        # Run Facebook account search and analysis on candidates with a linked or possible Facebook account
        number_of_candidates_to_search = 25
        current_candidate_index = 0
        while positive_value_exists(number_of_candidates_to_search) \
                and (current_candidate_index < candidate_list_count):
            one_candidate = candidate_list[current_candidate_index]
            # If the candidate has a facebook_url, but no facebook_profile_image_url_https,
            # see if we already tried to scrape them
            if positive_value_exists(one_candidate.facebook_url) \
                    and not positive_value_exists(one_candidate.facebook_profile_image_url_https):
                # Check to see if we have already tried to find their photo link from Facebook. We don't want to
                #  search Facebook more than once.
                request_history_query = RemoteRequestHistory.objects.filter(
                    candidate_campaign_we_vote_id__iexact=one_candidate.we_vote_id,
                    kind_of_action=RETRIEVE_POSSIBLE_FACEBOOK_PHOTOS)
                request_history_list = list(request_history_query)

                if not positive_value_exists(request_history_list):
                    add_messages = False
                    scrape_one_facebook_page(one_candidate, request, remote_request_history_manager, add_messages)
                    number_of_candidates_to_search -= 1
                else:
                    logger.info("Skipped URL: " + one_candidate.facebook_url)

            current_candidate_index += 1
    except CandidateCampaign.DoesNotExist:
        # This is fine, do nothing
        pass

    return HttpResponseRedirect(reverse('candidate:candidate_list', args=()) +
                                '?google_civic_election_id=' + str(google_civic_election_id) +
                                '&state_code=' + str(state_code) +
                                '&hide_candidate_tools=' + str(hide_candidate_tools) +
                                '&page=' + str(page)
                                )


@login_required
def scrape_and_save_facebook_photo_view(request):
    remote_request_history_manager = RemoteRequestHistoryManager()

    authority_required = {'verified_volunteer'}  # admin, verified_volunteer
    if not voter_has_authority(request, authority_required):
        return redirect_to_sign_in_page(request, authority_required)

    google_civic_election_id = convert_to_int(request.GET.get('google_civic_election_id', 0))
    hide_candidate_tools = request.GET.get('hide_candidate_tools', False)
    page = request.GET.get('page', 0)
    state_code = request.GET.get('state_code', '')
    candidate_we_vote_id = request.GET.get('candidate_we_vote_id', "")

    if not positive_value_exists(candidate_we_vote_id):
        messages.add_message(request, messages.ERROR,
                             'scrape_and_save_facebook_photo_view, Candidate not specified')
        return HttpResponseRedirect(reverse('candidate:candidate_list', args=()) +
                                    '?google_civic_election_id=' + str(google_civic_election_id) +
                                    '&state_code=' + str(state_code) +
                                    '&hide_candidate_tools=' + str(hide_candidate_tools) +
                                    '&page=' + str(page)
                                    )

    try:
        candidate_query = CandidateCampaign.objects.all()
        candidate_query = candidate_query.filter(we_vote_id__iexact=candidate_we_vote_id)
        candidate_list = list(candidate_query)
        one_candidate = candidate_list[0]

        # If the candidate has a facebook_url, but no facebook_profile_image_url_https,
        # see if we already tried to scrape them
        if not positive_value_exists(one_candidate.facebook_url):
            messages.add_message(request, messages.ERROR,
                                 'scrape_and_save_facebook_photo_view, No facebook_url found.')
            return HttpResponseRedirect(
                reverse('candidate:candidate_edit_we_vote_id', args=(one_candidate.we_vote_id,)) +
                '?google_civic_election_id=' + str(google_civic_election_id) +
                '&state_code=' + str(state_code) +
                '&hide_candidate_tools=' + str(hide_candidate_tools) +
                '&page=' + str(page)
                )

        add_messages = True
        scrape_one_facebook_page(one_candidate, request, remote_request_history_manager, add_messages)

    except CandidateCampaign.DoesNotExist:
        # This is fine, do nothing
        messages.add_message(request, messages.ERROR,
                             'scrape_and_save_facebook_photo_view, Candidate not found.')
        return HttpResponseRedirect(reverse('candidate:candidate_list', args=()) +
                                    '?google_civic_election_id=' + str(google_civic_election_id) +
                                    '&state_code=' + str(state_code) +
                                    '&hide_candidate_tools=' + str(hide_candidate_tools) +
                                    '&page=' + str(page)
                                    )

    return HttpResponseRedirect(reverse('candidate:candidate_edit_we_vote_id', args=(one_candidate.we_vote_id,)) +
                                '?google_civic_election_id=' + str(google_civic_election_id) +
                                '&state_code=' + str(state_code) +
                                '&hide_candidate_tools=' + str(hide_candidate_tools) +
                                '&page=' + str(page)
                                )
