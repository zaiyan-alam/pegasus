#  Copyright 2007-2014 University Of Southern California
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing,
#  software distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

__author__ = 'Rajiv Mayani'

import logging

import hashlib

from flask import g, request, make_response

from Pegasus.service import cache
from Pegasus.service.monitoring import monitoring_routes
from Pegasus.service.monitoring.queries import MasterWorkflowQueries
from Pegasus.service.monitoring.serializer import RootWorkflowSerializer

log = logging.getLogger(__name__)

JSON_HEADER = {'Content-Type': 'application/json'}


@monitoring_routes.url_value_preprocessor
def pull_m_wf_id(endpoint, values):
    """
    If the requested endpoint contains a value for m_wf_id variable then extract it and set it in g.m_wf_id.
    """
    if values and 'm_wf_id' in values:
        g.m_wf_id = values['m_wf_id']


@monitoring_routes.before_request
def compute_stampede_db_url():
    """
    If the requested endpoint requires connecting to a STAMPEDE database, then determine STAMPEDE DB URL and store it
    in g.stampede_db_url
    """
    if '/workflow' not in request.path or 'm_wf_id' not in g:
        return

    md5sum = hashlib.md5()
    md5sum.update(g.master_db_url)
    m_wf_id = g.m_wf_id

    del g.m_wf_id

    def _get_cache_key(key_suffix):
        return '%s.%s' % (md5sum.hexdigest(), key_suffix)

    cache_key = _get_cache_key(m_wf_id)

    if cache.get(cache_key):
        log.debug('Cache Hit: compute_stampede_db_url %s' % cache_key)
        g.stampede_db_url = cache.get(cache_key).db_url

    else:
        log.debug('Cache Miss: compute_stampede_db_url %s' % cache_key)
        queries = MasterWorkflowQueries(g.master_db_url)
        root_workflow = queries.get_root_workflow(m_wf_id)
        queries.close()

        g.stampede_db_url = root_workflow.db_url

        cache.set(_get_cache_key(root_workflow.wf_id), root_workflow, timeout=600)
        cache.set(_get_cache_key(root_workflow.wf_uuid), root_workflow, timeout=600)


@monitoring_routes.before_request
def get_query_args():
    g.query_args = {}

    def to_int(q_arg, value):
        try:
            return int(value)
        except ValueError:
            log.exception('Query Argument %s = %s is not a valid int' % (q_arg, value))
            abort(400)

    def to_str(q_arg, value):
        return value

    def to_bool(q_arg, value):
        return True if value.lower() == 'true' else False

    query_args = {
        'start-index': to_int,
        'max-results': to_int,
        'query': to_str,
        'order': to_str,
        'recent': to_bool,
        'pretty-print': to_bool
    }

    for arg, cast in query_args.iteritems():
        if arg in request.args:
            g.query_args[arg.replace('-', '_')] = cast(arg, request.args.get(arg))


"""
Root Workflow

{
    "wf_id"             : int:wf_id,
    "wf_uuid"           : string:wf_uuid,
    "submit_hostname"   : string:submit_hostname,
    "submit_dir"        : string:submit_dir,
    "planner_arguments" : string:planner_arguments,
    "planner_version"   : string:planner_version,
    "user"              : string:user,
    "grid_dn"           : string:grid_dn,
    "dax_label"         : string:dax_label,
    "dax_version"       : string:dax_version,
    "dax_file"          : string:dax_file,
    "dag_file_name"     : string:dag_file_name,
    "timestamp"         : int:timestamp,
    "workflow_state"    : object:workflow_state,
    "_links"            : {
        "workflow" : href:workflow
    }
}
"""


@monitoring_routes.route('/user/<string:username>/root')
@monitoring_routes.route('/user/<string:username>/root/query', methods=['POST'])
def get_root_workflows(username):
    """
    Returns a collection of root level workflows.

    :query int start-index: Return results starting from record <start-index> (0 indexed)
    :query int max-results: Return a maximum of <max-results> records
    :query string query: Search criteria
    :query string order: Sorting criteria
    :query boolean pretty-print: Return formatted JSON response.

    :statuscode 200: OK
    :statuscode 204: No content; when no workflows found.
    :statuscode 400: Bad request
    :statuscode 401: Authentication failure
    :statuscode 403: Authorization failure

    :return type: Collection
    :return resource: Root Workflow
    """
    queries = MasterWorkflowQueries(g.master_db_url)
    records, total_records, total_filtered = queries.get_root_workflows(**g.query_args)

    if total_records == 0:
        log.debug('Total records is 0; returning HTTP 204 No content')
        return make_response('', 204, JSON_HEADER)

    #
    # Generate JSON Response
    #
    serializer = RootWorkflowSerializer(**g.query_args)
    response_json = serializer.encode_collection(records, total_records, total_filtered)

    return make_response(response_json, 200, JSON_HEADER)


@monitoring_routes.route('/user/<string:username>/root/<string:m_wf_id>')
def get_root_workflow(username, m_wf_id):
    """
    Returns root level workflow identified by m_wf_id.

    :query boolean pretty-print: Return formatted JSON response.

    :statuscode 200: OK
    :statuscode 401: Authentication failure
    :statuscode 403: Authorization failure
    :statuscode 404: Not found

    :return type: Record
    :return resource: Root Workflow
    """
    pass


"""
Workflow

{
    "wf_id"             : int:wf_id,
    "root_wf_id"        : int:root_wf_id,
    "parent_wf_id"      : int:parent_wf_id,
    "wf_uuid"           : string:wf_uuid,
    "submit_hostname"   : string:submit_hostname,
    "submit_dir"        : string:submit_dir,
    "planner_arguments" : string:planner_arguments,
    "planner_version"   : string:planner_version,
    "user"              : string:user,
    "grid_dn"           : string:grid_dn,
    "dax_label"         : string:dax_label,
    "dax_version"       : string:dax_version,
    "dax_file"          : string:dax_file,
    "dag_file_name"     : string:dag_file_name,
    "timestamp"         : int:timestamp,
    "_links"            : {
        "workflow_state" : href:workflow_state,
        "job"            : href:job,
        "task"           : href:task,
        "host"           : href:host,
        "invocation"     : href:invocation
    }
}
"""


@monitoring_routes.route('/user/<string:username>/root/<string:m_wf_id>/workflow')
@monitoring_routes.route('/user/<string:username>/root//<string:m_wf_id>/workflow/query', methods=['POST'])
def get_workflows(username, m_wf_id):
    pass


@monitoring_routes.route('/user/<string:username>/root/<string:m_wf_id>/workflow/<string:wf_id>')
def get_workflow(username, m_wf_id, wf_id):
    pass


"""
{
    "state"         : string:state,
    "status"        : int:status,
    "restart_count" : int:restart_count,
    "timestamp"     : datetime:timestamp,
    "_links"          : {
        "workflow"     : "<href:workflow>"
    }
}
"""

"""
Job

{
    "job_id"      : int: job_id,
    "exec_job_id" : string: exec_job_id,
    "submit_file" : string: submit_file,
    "type_desc"   : string: type_desc,
    "max_retries" : int: max_retries,
    "clustered"   : bool: clustered,
    "task_count"  : int: task_count,
    "executable"  : string: executable,
    "argv"        : string: argv,
    "_links"      : {
        "workflow"     : href:workflow,
        "task"         : href:task,
        "job_instance" : href:job_instance
    }
}
"""

"""
Host

    {
    "host_id"      : int:host_id,
    "site_name"    : string:site_name,
    "hostname"     : string:hostname,
    "ip"           : string:ip,
    "uname"        : string:uname,
    "total_memory" : string:total_memory,
    "_links"       : {
        "workflow"     : href:workflow,
        "job_instance" : href:job_instance
    }
}
"""

"""
Job State

{
    "job_instance_id"     : "<int:job_instance_id>",
    "state"               : "<string:state>",
    "jobstate_submit_seq" : "<int:jobstate_submit_seq>",
    "timestamp"           : "<int:timestamp>",
    "_links"              : {
        "job_instance" : "href:job_instance"
    }
}
"""

"""
Task

{
    "task_id"        : int:task_id,
    "abs_task_id"    : string:abs_task_id,
    "type_desc"      : string: type_desc,
    "transformation" : string:transformation,
    "argv"           : string:argv,
    "_links"         : {
        "workflow" : href:workflow,
        "job"      : href:job
    }
}
"""

"""
Job Instance

{
    "job_instance_id"   : int:job_instance_id,
    "host_id"           : int:host_id,
    "job_submit_seq"    : int:job_submit_seq,
    "sched_id"          : string:sched_id,
    "site_name"         : string:site_name,
    "user"              : string:user,
    "work_dir"          : string:work_dir,
    "cluster_start"     : int:cluster_start,
    "cluster_duration"  : int:cluster_duration,
    "local_duration"    : int:local_duration,
    "subwf_id"          : int:subwf_id,
    "stdout_text"       : string:stdout_text,
    "stderr_text"       : string:stderr_text,
    "stdin_file"        : string:stdin_file,
    "stdout_file"       : string:stdout_file,
    "stderr_file"       : string:stderr_file,
    "multiplier_factor" : int:multiplier_factor,
    "_links"            : {
        "job_state"  : href:job_state,
        "host"       : href:host,
        "invocation" : href:invocation,
        "job"        : href:job
    }
}
"""

"""
Invocation

{
    "invocation_id"   : int:invocation_id,
    "job_instance_id" : int:job_instance_id,
    "abs_task_id"     : string:abs_task_id,
    "task_submit_seq" : int:task_submit_seq,
    "start_time"      : int:start_time,
    "remote_duration" : int:remote_duration,
    "remote_cpu_time" : int:remote_cpu_time,
    "exitcode"        : int:exitcode,
    "transformation"  : string:transformation,
    "executable"      : string:executable,
    "argv"            : string:argv,
    "_links"          : {
        "workflow"     : href:workflow,
        "job_instance" : href:job_instance
    }
}
"""


@monitoring_routes.errorhandler(404)
def page_not_found(error):
    pass


@monitoring_routes.errorhandler(BaseException)
def master_database_missing(error):
    pass
