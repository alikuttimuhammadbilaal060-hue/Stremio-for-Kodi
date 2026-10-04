#!/usr/bin/env python3
"""Sync repository issues into MKGA Lab and execute verified MKGA resolution actions.

GitHub write credentials never leave GitHub Actions. MKGA receives issue content via the
existing RELEASE_SYNC_TOKEN and returns only queued reply/close actions after Lab has
recorded deployed + passing test/review evidence.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY = os.environ.get('GITHUB_REPOSITORY', '0eroiQ/Stremio-for-Kodi')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
MKGA_TOKEN = os.environ.get('MKGA_RELEASE_SYNC_TOKEN', '')
MKGA_BASE = 'https://mkga.tv/api/github/stremio-kodi/issues'
MAX_RESPONSE = 2 * 1024 * 1024

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError('Unexpected redirect')

def request_json(url, method='GET', body=None, github=False):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Unsafe URL')
    headers = {'Accept': 'application/vnd.github+json', 'Content-Type': 'application/json',
               'User-Agent': 'stremio-for-kodi-mkga-issue-sync'}
    if github:
        headers.update({'Authorization': 'Bearer ' + GITHUB_TOKEN, 'X-GitHub-Api-Version': '2022-11-28'})
    else:
        headers['Authorization'] = 'Bearer ' + MKGA_TOKEN
    data = None if body is None else json.dumps(body, separators=(',', ':')).encode('utf-8')
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=30) as response:
        raw = response.read(MAX_RESPONSE + 1)
    if len(raw) > MAX_RESPONSE:
        raise ValueError('Response too large')
    return json.loads(raw or b'{}')

def github(path, method='GET', body=None):
    return request_json('https://api.github.com' + path, method, body, github=True)

def mkga(path, method='GET', body=None):
    return request_json(MKGA_BASE + path, method, body, github=False)

def all_issues():
    result = []
    for page in range(1, 11):
        rows = github('/repos/{}/issues?state=all&per_page=100&page={}'.format(REPOSITORY, page))
        if not isinstance(rows, list):
            raise RuntimeError('Unexpected GitHub issues response')
        for item in rows:
            if item.get('pull_request'):
                continue
            result.append({
                'number': int(item['number']),
                'title': str(item.get('title') or '')[:160],
                'body': str(item.get('body') or '')[:12000],
                'state': 'closed' if item.get('state') == 'closed' else 'open',
                'html_url': str(item.get('html_url') or ''),
                'updated_at': str(item.get('updated_at') or ''),
                'labels': [str(v if isinstance(v, str) else v.get('name') or '')[:80]
                           for v in item.get('labels') or [] if (v if isinstance(v, str) else v.get('name'))]
            })
        if len(rows) < 100:
            break
    return result

def sync_issues(issues):
    created = updated = 0
    for start in range(0, len(issues), 25):
        response = mkga('/sync', 'POST', {'issues': issues[start:start + 25]})
        created += int(response.get('created') or 0)
        updated += int(response.get('updated') or 0)
    print('MKGA issue sync: total={} created={} updated={}'.format(len(issues), created, updated))

def issue_comments(number):
    rows = []
    for page in range(1, 6):
        batch = github('/repos/{}/issues/{}/comments?per_page=100&page={}'.format(REPOSITORY, number, page))
        if not isinstance(batch, list):
            break
        rows.extend(batch)
        if len(batch) < 100:
            break
    return rows

def action_marker(action_id):
    if not re.fullmatch(r'[A-Za-z0-9-]{20,80}', str(action_id)):
        raise ValueError('Invalid action id')
    return '<!-- mkga-action:{} -->'.format(action_id)

def ack(action_id, ok, error=''):
    return mkga('/actions/{}/ack'.format(urllib.parse.quote(str(action_id), safe='')), 'POST',
                {'ok': bool(ok), 'error': str(error)[-1000:]})

def execute_actions():
    data = mkga('/actions')
    actions = data.get('actions') or []
    completed = failed = 0
    for action in actions:
        action_id = str(action.get('id') or '')
        number = int(action.get('issueNumber') or 0)
        try:
            if number < 1:
                raise ValueError('Invalid issue number')
            marker = action_marker(action_id)
            existing = any(marker in str(c.get('body') or '') for c in issue_comments(number))
            if not existing:
                body = str(action.get('comment') or '').strip()
                if not body:
                    raise ValueError('Empty resolution comment')
                github('/repos/{}/issues/{}/comments'.format(REPOSITORY, number), 'POST',
                       {'body': body + '\n\n' + marker})
            issue = github('/repos/{}/issues/{}'.format(REPOSITORY, number))
            if action.get('close') and issue.get('state') != 'closed':
                github('/repos/{}/issues/{}'.format(REPOSITORY, number), 'PATCH',
                       {'state': 'closed', 'state_reason': 'completed'})
            ack(action_id, True)
            completed += 1
        except Exception as error:
            try:
                ack(action_id, False, '{}: {}'.format(type(error).__name__, error))
            except Exception:
                pass
            print('issue action failed #{}: {}'.format(number, type(error).__name__), file=sys.stderr)
            failed += 1
    print('MKGA issue actions: completed={} failed={}'.format(completed, failed))
    if failed:
        raise RuntimeError('{} MKGA issue action(s) failed'.format(failed))

def main():
    if REPOSITORY != '0eroiQ/Stremio-for-Kodi' or not GITHUB_TOKEN or not MKGA_TOKEN:
        raise RuntimeError('Expected repository and workflow credentials are required')
    issues = all_issues()
    sync_issues(issues)
    execute_actions()

if __name__ == '__main__':
    main()
