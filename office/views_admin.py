# office/views_admin.py
# Brought to you by We Vote. Be good.
# -*- coding: UTF-8 -*-

from .controllers import offices_import_from_master_server, fetch_duplicate_office_count, \
    find_duplicate_contest_office, figure_out_conflict_values
from .models import ContestOffice, ContestOfficeManager, CONTEST_OFFICE_UNIQUE_IDENTIFIERS
from admin_tools.views import redirect_to_sign_in_page
from ballot.controllers import move_ballot_items_to_another_office
from bookmark.models import BookmarkItemList
from candidate.controllers import move_candidates_to_another_office
from candidate.models import CandidateCampaign, fetch_candidate_count_for_office
from config.base import get_environment_variable
from django.http import HttpResponseRedirect
from django.core.urlresolvers import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.messages import get_messages
from django.shortcuts import render
from django.db.models import Q
from election.models import Election, ElectionManager
from exception.models import handle_record_found_more_than_one_exception,\
    handle_record_not_found_exception, handle_record_not_saved_exception
from office.models import ContestOfficeListManager
from position.controllers import move_positions_to_another_office
from position.models import OPPOSE, PositionListManager, SUPPORT
from voter.models import voter_has_authority
import wevote_functions.admin
from wevote_functions.functions import convert_to_int, positive_value_exists, STATE_CODE_MAP
from django.http import HttpResponse
import json

OFFICES_SYNC_URL = get_environment_variable("OFFICES_SYNC_URL")  # officesSyncOut
WE_VOTE_SERVER_ROOT_URL = get_environment_variable("WE_VOTE_SERVER_ROOT_URL")

logger = wevote_functions.admin.get_logger(__name__)


# This page does not need to be protected.
# NOTE: @login_required() throws an error. Needs to be figured out if we ever want to secure this page.
# class OfficesSyncOutView(APIView):
#     def get(self, request, format=None):
def offices_sync_out_view(request):  # officesSyncOut
    google_civic_election_id = convert_to_int(request.GET.get('google_civic_election_id', 0))
    state_code = request.GET.get('state_code', '')

    try:
        contest_office_list = ContestOffice.objects.using('readonly').all()
        if positive_value_exists(google_civic_election_id):
            contest_office_list = contest_office_list.filter(google_civic_election_id=google_civic_election_id)
        if positive_value_exists(state_code):
            contest_office_list = contest_office_list.filter(state_code__iexact=state_code)
        # serializer = ContestOfficeSerializer(contest_office_list, many=True)
        # return Response(serializer.data)
        # get the data using values_list
        contest_office_list_dict = contest_office_list.values('we_vote_id', 'office_name', 'google_civic_election_id',
                                                              'ocd_division_id', 'maplight_id',
                                                              'ballotpedia_id', 'ballotpedia_office_id',
                                                              'ballotpedia_office_name', 'ballotpedia_office_url',
                                                              'ballotpedia_race_id', 'ballotpedia_race_office_level',
                                                              'wikipedia_id', 'number_voting_for', 'number_elected',
                                                              'state_code', 'primary_party', 'district_name',
                                                              'district_scope', 'district_id', 'contest_level0',
                                                              'contest_level1', 'contest_level2',
                                                              'electorate_specifications', 'special', 'state_code')
        if contest_office_list_dict:
            contest_office_list_json = list(contest_office_list_dict)
            return HttpResponse(json.dumps(contest_office_list_json), content_type='application/json')
    except ContestOffice.DoesNotExist:
        pass

    json_data = {
        'success': False,
        'status': 'CONTEST_OFFICE_MISSING'
    }
    return HttpResponse(json.dumps(json_data), content_type='application/json')


@login_required
def offices_import_from_master_server_view(request):
    # admin, partner_organization, political_data_manager, political_data_viewer, verified_volunteer
    authority_required = {'admin'}
    if not voter_has_authority(request, authority_required):
        return redirect_to_sign_in_page(request, authority_required)

    if WE_VOTE_SERVER_ROOT_URL in OFFICES_SYNC_URL:
        messages.add_message(request, messages.ERROR, "Cannot sync with Master We Vote Server -- "
                                                      "this is the Master We Vote Server.")
        return HttpResponseRedirect(reverse('admin_tools:admin_home', args=()))

    google_civic_election_id = convert_to_int(request.GET.get('google_civic_election_id', 0))
    state_code = request.GET.get('state_code', '')

    results = offices_import_from_master_server(request, google_civic_election_id, state_code)

    if not results['success']:
        messages.add_message(request, messages.ERROR, results['status'])
    else:
        messages.add_message(request, messages.INFO, 'Offices import completed. '
                                                     'Saved: {saved}, Updated: {updated}, '
                                                     'Duplicates skipped: '
                                                     '{duplicates_removed}, '
                                                     'Not processed: {not_processed}'
                                                     ''.format(saved=results['saved'],
                                                               updated=results['updated'],
                                                               duplicates_removed=results['duplicates_removed'],
                                                               not_processed=results['not_processed']))
    return HttpResponseRedirect(reverse('admin_tools:sync_dashboard', args=()) + "?google_civic_election_id=" +
                                str(google_civic_election_id) + "&state_code=" + str(state_code))


@login_required
def office_list_view(request):
    # admin, partner_organization, political_data_manager, political_data_viewer, verified_volunteer
    authority_required = {'partner_organization', 'verified_volunteer'}
    if not voter_has_authority(request, authority_required):
        return redirect_to_sign_in_page(request, authority_required)

    google_civic_election_id = convert_to_int(request.GET.get('google_civic_election_id', 0))
    state_code = request.GET.get('state_code', '')
    show_all = request.GET.get('show_all', False)
    show_all_elections = request.GET.get('show_all_elections', False)
    office_search = request.GET.get('office_search', '')

    office_list_found = False
    office_list = []
    updated_office_list = []
    office_list_count = 0
    try:
        office_queryset = ContestOffice.objects.all()
        if positive_value_exists(google_civic_election_id):
            office_queryset = office_queryset.filter(google_civic_election_id=google_civic_election_id)
        else:
            # TODO Limit this search to upcoming_elections only
            pass
        if positive_value_exists(state_code):
            office_queryset = office_queryset.filter(state_code__iexact=state_code)
        office_queryset = office_queryset.order_by("office_name")

        if positive_value_exists(office_search):
            search_words = office_search.split()
            for one_word in search_words:
                filters = []  # Reset for each search word
                new_filter = Q(office_name__icontains=one_word)
                filters.append(new_filter)

                new_filter = Q(we_vote_id__icontains=one_word)
                filters.append(new_filter)

                new_filter = Q(wikipedia_id__icontains=one_word)
                filters.append(new_filter)

                # Add the first query
                if len(filters):
                    final_filters = filters.pop()

                    # ...and "OR" the remaining items in the list
                    for item in filters:
                        final_filters |= item

                    office_queryset = office_queryset.filter(final_filters)

        office_list = list(office_queryset)

        if len(office_list):
            office_list_found = True
            status = 'OFFICES_RETRIEVED'
            success = True
        else:
            status = 'NO_OFFICES_RETRIEVED'
            success = True
    except ContestOffice.DoesNotExist:
        # No offices found. Not a problem.
        status = 'NO_OFFICES_FOUND_DoesNotExist'
        office_list = []
        success = True
    except Exception as e:
        status = 'FAILED retrieve_all_offices_for_upcoming_election ' \
                 '{error} [type: {error_type}]'.format(error=e, error_type=type(e))
        success = False

    if office_list_found:
        position_list_manager = PositionListManager()
        for office in office_list:
            office.candidate_count = fetch_candidate_count_for_office(office.id)
            office.positions_count = position_list_manager.fetch_public_positions_count_for_contest_office(
                office.id, office.we_vote_id)

            updated_office_list.append(office)

            office_list_count = len(updated_office_list)
            if office_list_count >= 500:
                # Limit to showing only 500
                break

    election_manager = ElectionManager()
    if positive_value_exists(show_all_elections):
        results = election_manager.retrieve_elections()
        election_list = results['election_list']
    else:
        results = election_manager.retrieve_upcoming_elections()
        election_list = results['election_list']

    state_list = STATE_CODE_MAP
    sorted_state_list = sorted(state_list.items())

    status_print_list = ""
    status_print_list += "office_list_count: " + \
                         str(office_list_count) + " "

    messages.add_message(request, messages.INFO, status_print_list)

    messages_on_stage = get_messages(request)

    template_values = {
        'messages_on_stage':        messages_on_stage,
        'office_list':              updated_office_list,
        'office_search':            office_search,
        'election_list':            election_list,
        'state_code':               state_code,
        'show_all_elections':       show_all_elections,
        'state_list':               sorted_state_list,
        'google_civic_election_id': google_civic_election_id,
    }
    return render(request, 'office/office_list.html', template_values)


@login_required
def office_new_view(request):
    authority_required = {'verified_volunteer'}  # admin, verified_volunteer
    if not voter_has_authority(request, authority_required):
        return redirect_to_sign_in_page(request, authority_required)

    google_civic_election_id = request.GET.get('google_civic_election_id', 0)
    state_code = request.GET.get('state_code', "")

    office_list_manager = ContestOfficeListManager()
    updated_office_list = []
    results = office_list_manager.retrieve_all_offices_for_upcoming_election(google_civic_election_id, state_code, True)
    if results['office_list_found']:
        office_list = results['office_list_objects']
        for office in office_list:
            office.candidate_count = fetch_candidate_count_for_office(office.id)
            updated_office_list.append(office)

    messages_on_stage = get_messages(request)
    template_values = {
        'messages_on_stage':        messages_on_stage,
        'google_civic_election_id': google_civic_election_id,
        'office_list':              updated_office_list,
    }
    return render(request, 'office/office_edit.html', template_values)


@login_required
def office_edit_view(request, office_id=0, contest_office_we_vote_id=""):
    authority_required = {'verified_volunteer'}  # admin, verified_volunteer
    if not voter_has_authority(request, authority_required):
        return redirect_to_sign_in_page(request, authority_required)

    messages_on_stage = get_messages(request)
    office_id = convert_to_int(office_id)
    google_civic_election_id = request.GET.get('google_civic_election_id', 0)

    office_on_stage = ContestOffice()
    office_on_stage_found = False
    try:
        if positive_value_exists(office_id):
            office_on_stage = ContestOffice.objects.get(id=office_id)
        else:
            office_on_stage = ContestOffice.objects.get(we_vote_id=contest_office_we_vote_id)
        office_on_stage_found = True
    except ContestOffice.MultipleObjectsReturned as e:
        handle_record_found_more_than_one_exception(e, logger=logger)
    except ContestOffice.DoesNotExist:
        # This is fine, create new
        pass

    if office_on_stage_found:
        # Was a contest_office_merge_possibility_found?
        office_on_stage.contest_office_merge_possibility_found = True  # TODO DALE Make dynamic
        template_values = {
            'messages_on_stage':        messages_on_stage,
            'office':                   office_on_stage,
            'google_civic_election_id': google_civic_election_id,
        }
    else:
        template_values = {
            'messages_on_stage':        messages_on_stage,
            'google_civic_election_id': google_civic_election_id,
        }
    return render(request, 'office/office_edit.html', template_values)


@login_required
def office_edit_process_view(request):
    """
    Process the new or edit office forms
    :param request:
    :return:
    """
    authority_required = {'verified_volunteer'}  # admin, verified_volunteer
    if not voter_has_authority(request, authority_required):
        return redirect_to_sign_in_page(request, authority_required)

    office_id = convert_to_int(request.POST.get('office_id', 0))
    office_name = request.POST.get('office_name', False)
    google_civic_office_name = request.POST.get('google_civic_office_name', False)
    google_civic_election_id = request.POST.get('google_civic_election_id', 0)
    ocd_division_id = request.POST.get('ocd_division_id', False)
    primary_party = request.POST.get('primary_party', False)
    state_code = request.POST.get('state_code', False)
    ballotpedia_office_id = request.POST.get('ballotpedia_office_id', False)  # Related to elected_office
    ballotpedia_race_id = request.POST.get('ballotpedia_race_id', False)  # Related to contest_office
    ballotpedia_office_name = request.POST.get('ballotpedia_office_name', False)
    remove_duplicate_process = request.POST.get('remove_duplicate_process', False)
    redirect_to_contest_office_list = convert_to_int(request.POST['redirect_to_contest_office_list'])

    election_state = ''
    if state_code is not False:
        election_state = state_code
    elif google_civic_election_id:
        election_manager = ElectionManager()
        results = election_manager.retrieve_election(google_civic_election_id)
        if results['election_found']:
            election = results['election']
            election_state = election.get_election_state()

    # Check to see if this office is already in the database
    office_on_stage_found = False
    try:
        office_query = ContestOffice.objects.filter(id=office_id)
        if len(office_query):
            office_on_stage = office_query[0]
            office_on_stage_found = True
    except Exception as e:
        handle_record_not_found_exception(e, logger=logger)

    try:
        if office_on_stage_found:
            # Update
            # Removed for now: convert_to_int(office_on_stage.google_civic_election_id) >= 1000000 and
            if office_name is not False:
                office_on_stage.office_name = office_name
            if google_civic_office_name is not False:
                office_on_stage.google_civic_office_name = google_civic_office_name
            if ocd_division_id is not False:
                office_on_stage.ocd_division_id = ocd_division_id
            if primary_party is not False:
                office_on_stage.primary_party = primary_party
            if positive_value_exists(election_state):
                office_on_stage.state_code = election_state
            if ballotpedia_office_id is not False:
                office_on_stage.ballotpedia_office_id = convert_to_int(ballotpedia_office_id)
            if ballotpedia_office_name is not False:
                office_on_stage.ballotpedia_office_name = ballotpedia_office_name
            if ballotpedia_race_id is not False:
                office_on_stage.ballotpedia_race_id = convert_to_int(ballotpedia_race_id)
            office_on_stage.save()
            office_on_stage_id = office_on_stage.id
            messages.add_message(request, messages.INFO, 'Office updated.')
            google_civic_election_id = office_on_stage.google_civic_election_id

            return HttpResponseRedirect(reverse('office:office_summary', args=(office_on_stage_id,)) +
                                        "?google_civic_election_id=" + str(google_civic_election_id) +
                                        "&state_code=" + str(state_code))
        else:
            # Create new
            office_on_stage = ContestOffice(
                office_name=office_name,
                google_civic_election_id=google_civic_election_id,
                state_code=election_state,
            )
            # Removing this limitation: convert_to_int(office_on_stage.google_civic_election_id) >= 1000000 and
            if google_civic_office_name is not False:
                office_on_stage.google_civic_office_name = google_civic_office_name
            if ocd_division_id is not False:
                office_on_stage.ocd_division_id = ocd_division_id
            if primary_party is not False:
                office_on_stage.primary_party = primary_party
            if ballotpedia_office_id is not False:
                office_on_stage.ballotpedia_office_id = convert_to_int(ballotpedia_office_id)
            if ballotpedia_office_name is not False:
                office_on_stage.ballotpedia_office_name = ballotpedia_office_name
            if ballotpedia_race_id is not False:
                office_on_stage.ballotpedia_race_id = convert_to_int(ballotpedia_race_id)
            office_on_stage.save()
            messages.add_message(request, messages.INFO, 'New office saved.')

            # Come back to the "Create New Office" page
            return HttpResponseRedirect(reverse('office:office_new', args=()) +
                                        "?google_civic_election_id=" + str(google_civic_election_id) +
                                        "&state_code=" + str(state_code))
    except Exception as e:
        handle_record_not_saved_exception(e, logger=logger)
        messages.add_message(request, messages.ERROR, 'Could not save office.')

    if redirect_to_contest_office_list:
        return HttpResponseRedirect(reverse('office:office_list', args=()) +
                                    '?google_civic_election_id=' + str(google_civic_election_id) +
                                    '&state_code=' + str(state_code))

    if remove_duplicate_process:
        return HttpResponseRedirect(reverse('office:find_and_remove_duplicate_offices', args=()) +
                                    "?google_civic_election_id=" + str(google_civic_election_id) +
                                    "&state_code=" + str(state_code))
    else:
        return HttpResponseRedirect(reverse('office:office_edit', args=(office_id,)))


@login_required
def office_summary_view(request, office_id):
    # admin, partner_organization, political_data_manager, political_data_viewer, verified_volunteer
    authority_required = {'partner_organization', 'verified_volunteer'}
    if not voter_has_authority(request, authority_required):
        return redirect_to_sign_in_page(request, authority_required)

    messages_on_stage = get_messages(request)
    office_id = convert_to_int(office_id)
    office_on_stage_found = False
    google_civic_election_id = convert_to_int(request.GET.get('google_civic_election_id', 0))
    state_code = request.GET.get('state_code', "")
    try:
        office_on_stage = ContestOffice.objects.get(id=office_id)
        office_on_stage_found = True
        google_civic_election_id = office_on_stage.google_civic_election_id
    except ContestOffice.MultipleObjectsReturned as e:
        handle_record_found_more_than_one_exception(e, logger=logger)
    except ContestOffice.DoesNotExist:
        # This is fine, create new
        pass

    candidate_list_modified = []
    position_list_manager = PositionListManager()
    try:
        candidate_list = CandidateCampaign.objects.filter(contest_office_id=office_id)
        if positive_value_exists(google_civic_election_id):
            candidate_list = candidate_list.filter(google_civic_election_id=google_civic_election_id)
        candidate_list = candidate_list.order_by('candidate_name')
        support_total = 0
        for one_candidate in candidate_list:
            # Find the count of Voters that support this candidate (Organizations are not included in this)
            one_candidate.support_count = position_list_manager.fetch_voter_positions_count_for_candidate_campaign(
                one_candidate.id, "", SUPPORT)
            one_candidate.oppose_count = position_list_manager.fetch_voter_positions_count_for_candidate_campaign(
                one_candidate.id, "", OPPOSE)
            support_total += one_candidate.support_count

        for one_candidate in candidate_list:
            if positive_value_exists(support_total):
                percentage_of_support_number = one_candidate.support_count / support_total * 100
                one_candidate.percentage_of_support = "%.1f" % percentage_of_support_number

            candidate_list_modified.append(one_candidate)

    except CandidateCampaign.DoesNotExist:
        # This is fine, create new
        pass

    election_list = Election.objects.order_by('-election_day_text')

    if positive_value_exists(google_civic_election_id):
        election = Election.objects.get(google_civic_election_id=google_civic_election_id)

    if office_on_stage_found:
        template_values = {
            'messages_on_stage':        messages_on_stage,
            'office':                   office_on_stage,
            'candidate_list':           candidate_list_modified,
            'state_code':               state_code,
            'election':                 election,
            'election_list':            election_list,
            'google_civic_election_id': google_civic_election_id,
        }
    else:
        template_values = {
            'messages_on_stage': messages_on_stage,
        }
    return render(request, 'office/office_summary.html', template_values)


@login_required
def office_delete_process_view(request):
    authority_required = {'verified_volunteer'}  # admin, verified_volunteer
    if not voter_has_authority(request, authority_required):
        return redirect_to_sign_in_page(request, authority_required)

    office_id = convert_to_int(request.GET.get('office_id', 0))
    google_civic_election_id = convert_to_int(request.GET.get('google_civic_election_id', 0))

    office_on_stage_found = False
    office_on_stage = ContestOffice()
    try:
        office_on_stage = ContestOffice.objects.get(id=office_id)
        office_on_stage_found = True
        google_civic_election_id = office_on_stage.google_civic_election_id
    except ContestOffice.MultipleObjectsReturned as e:
        pass
    except ContestOffice.DoesNotExist:
        pass

    candidates_found_for_this_office = False
    if office_on_stage_found:
        try:
            candidate_list = CandidateCampaign.objects.filter(contest_office_id=office_id)
            # if positive_value_exists(google_civic_election_id):
            #     candidate_list = candidate_list.filter(google_civic_election_id=google_civic_election_id)
            candidate_list = candidate_list.order_by('candidate_name')
            if len(candidate_list):
                candidates_found_for_this_office = True
        except CandidateCampaign.DoesNotExist:
            pass

    try:
        if not candidates_found_for_this_office:
            # Delete the office
            office_on_stage.delete()
            messages.add_message(request, messages.INFO, 'Office deleted.')
        else:
            messages.add_message(request, messages.ERROR, 'Could not delete -- '
                                                          'candidates still attached to this office.')
            return HttpResponseRedirect(reverse('office:office_summary', args=(office_id,)))
    except Exception as e:
        messages.add_message(request, messages.ERROR, 'Could not delete office -- exception.')
        return HttpResponseRedirect(reverse('office:office_summary', args=(office_id,)))

    return HttpResponseRedirect(reverse('office:office_list', args=()) +
                                "?google_civic_election_id=" + str(google_civic_election_id))


@login_required
def find_duplicate_office_view(request, office_id=0):
    authority_required = {'verified_volunteer'}  # admin, verified_volunteer
    if not voter_has_authority(request, authority_required):
        return redirect_to_sign_in_page(request, authority_required)

    office_list = []

    number_of_duplicate_contest_offices_processed = 0
    number_of_duplicate_contest_offices_failed = 0
    number_of_duplicates_could_not_process = 0

    google_civic_election_id = request.GET.get('google_civic_election_id', 0)
    google_civic_election_id = convert_to_int(google_civic_election_id)

    contest_office_manager = ContestOfficeManager()
    contest_office_results = contest_office_manager.retrieve_contest_office_from_id(office_id)
    if not contest_office_results['contest_office_found']:
        messages.add_message(request, messages.ERROR, "Contest Office not found.")
        return HttpResponseRedirect(reverse('office:office_list', args=()) +
                                    "?google_civic_election_id=" + str(google_civic_election_id))

    contest_office = contest_office_results['contest_office']

    if not positive_value_exists(google_civic_election_id):
        messages.add_message(request, messages.ERROR,
                             "Contest Office must have a google_civic_election_id in order to merge.")
        return HttpResponseRedirect(reverse('office:office_edit', args=(office_id,)))

    ignore_office_id_list = []
    ignore_office_id_list.append(contest_office.we_vote_id)

    results = find_duplicate_contest_office(contest_office, ignore_office_id_list)

    # If we find contest offices to merge, stop and ask for confirmation
    if results['contest_office_merge_possibility_found']:
        contest_office_option1_for_template = contest_office
        contest_office_option2_for_template = results['contest_office_merge_possibility']

        # This view function takes us to displaying a template
        return render_contest_office_merge_form(request, contest_office_option1_for_template,
                                                contest_office_option2_for_template,
                                                results['contest_office_merge_conflict_values'])

    message = "Google Civic Election ID: {election_id}, " \
              "{number_of_duplicate_contest_offices_processed} duplicates processed, " \
              "{number_of_duplicate_contest_offices_failed} duplicate merges failed, " \
              "{number_of_duplicates_could_not_process} could not be processed because 3 exist " \
              "".format(election_id=google_civic_election_id,
                        number_of_duplicate_contest_offices_processed=number_of_duplicate_contest_offices_processed,
                        number_of_duplicate_contest_offices_failed=number_of_duplicate_contest_offices_failed,
                        number_of_duplicates_could_not_process=number_of_duplicates_could_not_process)

    messages.add_message(request, messages.INFO, message)

    return HttpResponseRedirect(reverse('office:office_edit', args=(office_id,)) +
                                "?google_civic_election_id={var}".format(
                                var=google_civic_election_id))


@login_required
def find_and_remove_duplicate_offices_view(request):
    authority_required = {'verified_volunteer'}  # admin, verified_volunteer
    if not voter_has_authority(request, authority_required):
        return redirect_to_sign_in_page(request, authority_required)

    contest_office_list = []
    ignore_office_id_list = []
    find_duplicates_count = request.GET.get('find_duplicates_count', 0)
    google_civic_election_id = request.GET.get('google_civic_election_id', 0)
    google_civic_election_id = convert_to_int(google_civic_election_id)
    contest_office_manager = ContestOfficeManager()

    # We only want to process if a google_civic_election_id comes in
    if not positive_value_exists(google_civic_election_id):
        messages.add_message(request, messages.ERROR, "Google Civic Election ID required.")
        return HttpResponseRedirect(reverse('office:office_list', args=()))

    try:
        # We sort by ID so that the entry which was saved first becomes the "master"
        contest_office_query = ContestOffice.objects.order_by('id')
        contest_office_query = contest_office_query.filter(google_civic_election_id=google_civic_election_id)
        contest_office_list = list(contest_office_query)
    except ContestOffice.DoesNotExist:
        pass

    # Loop through all of the offices in this election to see how many have possible duplicates
    if positive_value_exists(find_duplicates_count):
        duplicate_office_count = 0
        for contest_office in contest_office_list:
            # Note that we don't reset the ignore_office_id_list, so we don't search for a duplicate both directions
            ignore_office_id_list.append(contest_office.we_vote_id)
            duplicate_office_count_temp = fetch_duplicate_office_count(contest_office,
                                                                       ignore_office_id_list)
            duplicate_office_count += duplicate_office_count_temp

        if positive_value_exists(duplicate_office_count):
            messages.add_message(request, messages.INFO, "There are approximately {duplicate_office_count} "
                                                         "possible duplicates."
                                                         "".format(duplicate_office_count=duplicate_office_count))

    # Loop through all of the contest offices in this election
    ignore_office_id_list = []
    for contest_office in contest_office_list:
        # Add current contest office entry to the ignore list
        ignore_office_id_list.append(contest_office.we_vote_id)
        # Now check to for other contest offices we have labeled as "not a duplicate"
        not_a_duplicate_list = contest_office_manager.fetch_offices_are_not_duplicates_list_we_vote_ids(
            contest_office.we_vote_id)

        ignore_office_id_list += not_a_duplicate_list

        results = find_duplicate_contest_office(contest_office, ignore_office_id_list)
        ignore_office_id_list = []

        # If we find contest offices to merge, stop and ask for confirmation
        if results['contest_office_merge_possibility_found']:
            contest_office_option1_for_template = contest_office
            contest_office_option2_for_template = results['contest_office_merge_possibility']

            # This view function takes us to displaying a template
            return render_contest_office_merge_form(request, contest_office_option1_for_template,
                                                    contest_office_option2_for_template,
                                                    results['contest_office_merge_conflict_values'])

    message = "Google Civic Election ID: {election_id}, " \
              "No duplicate contest offices found for this election." \
              "".format(election_id=google_civic_election_id)

    messages.add_message(request, messages.INFO, message)

    return HttpResponseRedirect(reverse('office:office_list', args=()) + "?google_civic_election_id={var}"
                                                                         "".format(var=google_civic_election_id))


def render_contest_office_merge_form(
        request, contest_office_option1_for_template, contest_office_option2_for_template,
        contest_office_merge_conflict_values):
    position_list_manager = PositionListManager()

    bookmark_item_list = BookmarkItemList()

    # Get positions counts for both offices
    contest_office_option1_for_template.public_positions_count = \
        position_list_manager.fetch_public_positions_count_for_contest_office(
            contest_office_option1_for_template.id, contest_office_option1_for_template.we_vote_id)
    contest_office_option1_for_template.friends_positions_count = \
        position_list_manager.fetch_friends_only_positions_count_for_contest_office(
            contest_office_option1_for_template.id, contest_office_option1_for_template.we_vote_id)
    # Bookmarks
    bookmark_results = bookmark_item_list.retrieve_bookmark_item_list_for_contest_office(
        contest_office_option1_for_template.we_vote_id)
    if bookmark_results['bookmark_item_list_found']:
        bookmark_item_list = bookmark_results['bookmark_item_list']
        contest_office_option1_bookmark_count = len(bookmark_item_list)
    else:
        contest_office_option1_bookmark_count = 0
    contest_office_option1_for_template.bookmarks_count = contest_office_option1_bookmark_count

    contest_office_option2_for_template.public_positions_count = \
        position_list_manager.fetch_public_positions_count_for_contest_office(
            contest_office_option2_for_template.id, contest_office_option2_for_template.we_vote_id)
    contest_office_option2_for_template.friends_positions_count = \
        position_list_manager.fetch_friends_only_positions_count_for_contest_office(
            contest_office_option2_for_template.id, contest_office_option2_for_template.we_vote_id)
    # Bookmarks
    bookmark_results = bookmark_item_list.retrieve_bookmark_item_list_for_contest_office(
        contest_office_option2_for_template.we_vote_id)
    if bookmark_results['bookmark_item_list_found']:
        bookmark_item_list = bookmark_results['bookmark_item_list']
        contest_office_option2_bookmark_count = len(bookmark_item_list)
    else:
        contest_office_option2_bookmark_count = 0
    contest_office_option2_for_template.bookmarks_count = contest_office_option2_bookmark_count

    messages_on_stage = get_messages(request)
    template_values = {
        'messages_on_stage':        messages_on_stage,
        'contest_office_option1':   contest_office_option1_for_template,
        'contest_office_option2':   contest_office_option2_for_template,
        'conflict_values':          contest_office_merge_conflict_values,
        'google_civic_election_id': contest_office_option1_for_template.google_civic_election_id,
    }
    return render(request, 'office/office_merge.html', template_values)


@login_required
def office_merge_process_view(request):
    """
    Process the merging of two offices
    :param request:
    :return:
    """
    authority_required = {'verified_volunteer'}  # admin, verified_volunteer
    if not voter_has_authority(request, authority_required):
        return redirect_to_sign_in_page(request, authority_required)

    contest_office_manager = ContestOfficeManager()

    merge = request.POST.get('merge', False)
    skip = request.POST.get('skip', False)

    # Contest office 1 is the one we keep, and Contest office 2 is the one we will merge into Contest office 1
    contest_office1_we_vote_id = request.POST.get('contest_office1_we_vote_id', 0)
    contest_office2_we_vote_id = request.POST.get('contest_office2_we_vote_id', 0)
    google_civic_election_id = request.POST.get('google_civic_election_id', 0)
    redirect_to_contest_office_list = request.POST.get('redirect_to_contest_office_list', False)
    remove_duplicate_process = request.POST.get('remove_duplicate_process', False)
    state_code = request.POST.get('state_code', '')

    if positive_value_exists(skip):
        results = contest_office_manager.update_or_create_contest_offices_are_not_duplicates(
            contest_office1_we_vote_id, contest_office2_we_vote_id)
        if not results['new_contest_offices_are_not_duplicates_created']:
            messages.add_message(request, messages.ERROR, 'Could not save contest_offices_are_not_duplicates entry: ' +
                                 results['status'])
        messages.add_message(request, messages.INFO, 'Prior contest offices skipped, and not merged.')
        return HttpResponseRedirect(reverse('office:find_and_remove_duplicate_offices', args=()) +
                                    "?google_civic_election_id=" + str(google_civic_election_id) +
                                    "&state_code=" + str(state_code))

    contest_office1_results = contest_office_manager.retrieve_contest_office_from_we_vote_id(contest_office1_we_vote_id)
    if contest_office1_results['contest_office_found']:
        contest_office1_on_stage = contest_office1_results['contest_office']
        contest_office1_id = contest_office1_on_stage.id
    else:
        messages.add_message(request, messages.ERROR, 'Could not retrieve office 1.')
        return HttpResponseRedirect(reverse('office:office_list', args=()) +
                                    '?google_civic_election_id=' + str(google_civic_election_id) +
                                    '&state_code=' + str(state_code))

    contest_office2_results = contest_office_manager.retrieve_contest_office_from_we_vote_id(contest_office2_we_vote_id)
    if contest_office2_results['contest_office_found']:
        contest_office2_on_stage = contest_office2_results['contest_office']
        contest_office2_id = contest_office2_on_stage.id
    else:
        messages.add_message(request, messages.ERROR, 'Could not retrieve contest office 2.')
        return HttpResponseRedirect(reverse('office:office_list', args=()) +
                                    '?google_civic_election_id=' + str(google_civic_election_id) +
                                    '&state_code=' + str(state_code))

    # TODO: Merge quick_info's office details in future
    # TODO: Migrate bookmarks
    bookmark_item_list = BookmarkItemList()
    bookmark_results = bookmark_item_list.retrieve_bookmark_item_list_for_contest_office(contest_office2_we_vote_id)
    if bookmark_results['bookmark_item_list_found']:
        messages.add_message(request, messages.ERROR, "Bookmarks found for Contest Office 2 - "
                                                      "automatic merge not working yet.")
        return HttpResponseRedirect(reverse('office:find_and_remove_duplicate_offices', args=()) +
                                    "?google_civic_election_id=" + str(google_civic_election_id) +
                                    "&state_code=" + str(state_code))

    # Merge attribute values
    conflict_values = figure_out_conflict_values(contest_office2_on_stage, contest_office2_on_stage)
    for attribute in CONTEST_OFFICE_UNIQUE_IDENTIFIERS:
        conflict_value = conflict_values.get(attribute, None)
        if conflict_value == "CONFLICT":
            choice = request.POST.get(attribute + '_choice', '')
            if contest_office2_we_vote_id == choice:
                setattr(contest_office1_on_stage, attribute, getattr(contest_office2_on_stage, attribute))
        elif conflict_value == "CONTEST_OFFICE2":
            setattr(contest_office1_on_stage, attribute, getattr(contest_office2_on_stage, attribute))

    # Merge candidate's office details
    candidates_results = move_candidates_to_another_office(contest_office2_id, contest_office2_we_vote_id,
                                                           contest_office1_id, contest_office1_we_vote_id)
    if not candidates_results['success']:
        messages.add_message(request, messages.ERROR, candidates_results['status'])
        return HttpResponseRedirect(reverse('office:find_and_remove_duplicate_offices', args=()) +
                                    "?google_civic_election_id=" + str(google_civic_election_id) +
                                    "&state_code=" + str(state_code))

    # Merge ballot item's office details
    ballot_items_results = move_ballot_items_to_another_office(contest_office2_id, contest_office2_we_vote_id,
                                                               contest_office1_id, contest_office1_we_vote_id)
    if not ballot_items_results['success']:
        messages.add_message(request, messages.ERROR, ballot_items_results['status'])
        return HttpResponseRedirect(reverse('office:find_and_remove_duplicate_offices', args=()) +
                                    "?google_civic_election_id=" + str(google_civic_election_id) +
                                    "&state_code=" + str(state_code))

    # Merge public positions
    public_positions_results = move_positions_to_another_office(contest_office2_id, contest_office2_we_vote_id,
                                                                contest_office1_id, contest_office1_we_vote_id,
                                                                True)
    if not public_positions_results['success']:
        messages.add_message(request, messages.ERROR, public_positions_results['status'])
        return HttpResponseRedirect(reverse('office:find_and_remove_duplicate_offices', args=()) +
                                    "?google_civic_election_id=" + str(google_civic_election_id) +
                                    "&state_code=" + str(state_code))

    # Merge friends-only positions
    friends_positions_results = move_positions_to_another_office(contest_office2_id, contest_office2_we_vote_id,
                                                                 contest_office1_id, contest_office1_we_vote_id,
                                                                 False)
    if not friends_positions_results['success']:
        messages.add_message(request, messages.ERROR, friends_positions_results['status'])
        return HttpResponseRedirect(reverse('office:find_and_remove_duplicate_offices', args=()) +
                                    "?google_civic_election_id=" + str(google_civic_election_id) +
                                    "&state_code=" + str(state_code))

    # Note: wait to wrap in try/except block
    contest_office1_on_stage.save()

    # Remove contest office 2
    contest_office2_on_stage.delete()

    if redirect_to_contest_office_list:
        return HttpResponseRedirect(reverse('office:office_list', args=()) +
                                    '?google_civic_election_id=' + str(google_civic_election_id) +
                                    '&state_code=' + str(state_code))

    if remove_duplicate_process:
        return HttpResponseRedirect(reverse('office:find_and_remove_duplicate_offices', args=()) +
                                    "?google_civic_election_id=" + str(google_civic_election_id) +
                                    "&state_code=" + str(state_code))

    return HttpResponseRedirect(reverse('office:office_edit', args=(contest_office1_on_stage.id,)))
