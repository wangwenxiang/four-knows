"""Independent quality checks for an actual mobile 23-hour report (no poster required)."""
import argparse
import json
import re
import hashlib
import sys
from datetime import datetime, timedelta
from pathlib import Path


def validate(directory: Path, publication=False):
    data = json.loads((directory / 'data/posts.json').read_text())
    report = json.loads((directory / 'data/run-report.json').read_text())
    acquired = json.loads((directory / 'data/acquisition.json').read_text())
    page = (directory / 'index.html').read_text()
    embedded = json.loads(re.search(r'const DATA=(.*?);\nconst channels=', page, re.S).group(1))
    errors = []
    def check(ok, message):
        if not ok:
            errors.append(message)
    start = datetime.fromisoformat(data['windowStart'])
    end = datetime.fromisoformat(data['fetchStartedAt'])
    check(end - start == timedelta(hours=23), 'Window is not exactly 23 hours')
    check(report['windowStart'] == data['windowStart'] and report['fetchStartedAt'] == data['fetchStartedAt'], 'Window metadata mismatch')
    check(acquired['windowStart'] == data['windowStart'] and acquired['fetchStartedAt'] == data['fetchStartedAt'], 'Acquisition is from another run')
    check(data.get('layout') == 'mobile' and embedded.get('preview') is False, 'Not a real mobile report')
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from scripts.fetch_ai_v_radar import load_experts, append_expansion_experts
    configured = append_expansion_experts(load_experts(root/'ai_key_people_watchlist_visual.html'), root/'config/ai_x_expansion_watchlist.json')
    configured_handles = {p.handle.casefold() for p in configured}
    expected = {x['handle'].casefold() for x in data['experts']}
    check(expected == configured_handles, 'Monitored accounts differ from active configuration')
    covered = {x['handle'].casefold() for r in acquired['results'] if r.get('ok') for x in r.get('experts', [])}
    check(expected == covered, 'Acquisition did not cover every monitored account')
    check(report['accountsRequested'] == report['accountsSucceeded'] == len(configured_handles) and report['accountsFailed'] == 0, 'Account acquisition incomplete')
    check(all(r.get('ok') for r in acquired['results']), 'A fetch failed')
    for fetch in acquired['results']:
        if fetch.get('experts') and len(fetch.get('tweets', [])) >= 40:
            check(fetch.get('completenessStrategy') == 'split-saturated-search', 'A saturated account batch was not split for completeness')
    check(report['xHotspotSearch']['directionsFailed'] == 0, 'Hotspot acquisition incomplete')
    check(report['editorial'].get('promptVersion') == 'codex-editorial-six-channels-v1', 'Six-channel semantic review missing')
    posts = data['posts']
    ids = [p['id'] for p in posts]
    check(len(ids) == len(set(ids)), 'Duplicate post IDs')
    originals = {p['id']: p for r in acquired['results'] for p in r.get('tweets', [])}
    reviewed = report['editorial'].get('reviewedPosts', [])
    reviewed_ids = [p['id'] for p in reviewed]
    check(len(reviewed_ids) == len(set(reviewed_ids)) == report['editorial']['candidates'], 'Editorial review coverage mismatch')
    check(set(ids).issubset(set(reviewed_ids)), 'Unreviewed content was displayed')
    duplicate_rows = report['editorial'].get('duplicateReposts', [])
    quality = report.get('finalQuality') or {}
    pre_quality_ids = set(quality.get('inputIds', ids))
    check(all(p['id'] not in pre_quality_ids and p['retainedId'] in pre_quality_ids for p in duplicate_rows), 'Exact duplicate audit mismatch')
    quality_dropped = quality.get('dropped', 0)
    check(len(posts) + quality_dropped + len(duplicate_rows) + report['editorial']['dropped'] == len(reviewed), 'Selection ledger does not balance')
    check(len(posts) == report['postsSelected'] == len(embedded['records']), 'Display count mismatch')
    check(quality.get('complete') is True and quality.get('version') == 'mobile-final-quality-v1', 'Final quality review missing or incomplete')
    check(data.get('finalQuality') == quality, 'Quality audit differs between data and run report')
    check(0 < len(posts) <= quality.get('limit', 0) <= 50, 'High-quality selection must contain at most 50 posts')
    check(data.get('selectionLimits') == {'perAuthor': 0, 'total': quality.get('limit')}, 'Selection cap differs from quality audit')
    decisions = quality.get('decisions', [])
    decision_ids = [r.get('id') for r in decisions]
    check(len(decision_ids) == len(set(decision_ids)) == quality.get('reviewed') and set(decision_ids) == pre_quality_ids, 'Final quality did not review every input')
    check({r.get('id') for r in decisions if r.get('selected')} == set(ids), 'Final decisions differ from displayed posts')
    check(all(r.get('reason') and r.get('evidence') and r.get('finalReason') for r in decisions), 'Missing per-post quality evidence')
    check(all(r.get('qualified') and r.get('score', 0) >= 75 for r in decisions if r.get('selected')), 'Selected post below quality floor')
    check(pre_quality_ids.issubset(set(reviewed_ids)), 'Quality input contains unreviewed sources')
    backup = directory / 'data/posts-before-quality.json'
    if backup.exists():
        original_pool = json.loads(backup.read_text())
        if original_pool.get('fetchStartedAt') == data['fetchStartedAt']:
            root = Path(__file__).resolve().parents[1]
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            from scripts.refine_ai_v_mobile import fingerprint
            check(quality.get('inputSha256') == fingerprint(original_pool['posts']), 'Quality review input differs from preserved full texts')
    shown = {r['id']: r for r in embedded['records']}
    channels = {'research','agent','enterprise','growth','creative','tools'}
    recruitment = re.compile(r'\b(?:we.re hiring|job openings?|apply to (?:join|be)|join our team)\b|招聘|岗位开放', re.I)
    channel_counts = {}
    for p in posts:
        pid = p['id']
        check(pid in originals and p.get('text') == originals[pid].get('text'), f'{pid}: source changed or absent from fresh fetch')
        check(start <= datetime.fromisoformat(p['createdAtIso']) <= end, f'{pid}: outside window')
        check(datetime.fromisoformat(p['createdAtBeijing']).utcoffset() == timedelta(hours=8), f'{pid}: wrong display timezone')
        check(p['expert']['handle'].casefold() != 'sama', f'{pid}: excluded author')
        evidence = p.get('editorial', {})
        check(evidence.get('technicalRelevant') is True and evidence.get('channel') in channels and bool(evidence.get('evidence')), f'{pid}: missing editorial evidence')
        check(shown.get(pid, {}).get('source') == p, f'{pid}: display source differs')
        check(shown.get(pid, {}).get('track') == evidence.get('channel'), f'{pid}: display channel differs')
        channel_counts[evidence.get('channel')] = channel_counts.get(evidence.get('channel'), 0) + 1
        contexts = [p, p.get('quotedTweet') or {}]
        for source in contexts:
            context = '\n'.join([str(source.get('text','')),str((source.get('article') or {}).get('title','')),str((source.get('article') or {}).get('previewText',''))])
            check(not recruitment.search(context), f'{pid}: recruitment audit failed')
    for marker in ('<details', '先看这三条', '编辑观察', '${esc(r.title)}', '${esc(r.summary)}', '条排版样本'):
        check(marker not in page, f'Unexpected hidden content / generated title / sample label: {marker}')
    check('font-size:13px;line-height:1.6' in page and 'font-size:16px;line-height:1.85' in page, 'Incorrect bilingual typography')
    avatar = report['avatars']
    check(avatar.get('coverage') == 1 and avatar.get('quotedCoverage') == 1, 'Avatar coverage incomplete')
    check(avatar.get('postsWithAvatar') == len(posts), 'Missing primary avatars')
    warnings = []
    if report['translation'].get('failed') or report['translation'].get('coverage') != 1:
        warnings.append('Translation fallback present; inspect affected original texts')
    if publication:
        from scripts.select_ai_v_mobile_poster import validate_selection, selection_fingerprint
        from scripts.finalize_ai_v_poster import validate_rgb_png
        selection = data.get('posterSelection') or {}
        try:
            rows = validate_selection(data, selection)
            check(selection.get('inputPostsSha256') == selection_fingerprint(posts), 'Stale poster selection')
            check(report.get('posterSelection') == selection, 'Poster selection metadata mismatch')
            poster = json.loads((directory/'data/poster.json').read_text())
            check([r['id'] for r in poster['stories']] == [r['id'] for r in rows], 'Poster is not the approved three stories')
            check(all(p['title']==r['title'] and p['summary']==r['summary'] for p,r in zip(poster['stories'],rows)), 'Poster copy differs from selected copy')
            check(poster['monitored']==len(expected) and poster['selected']==len(posts), 'Stale poster counts')
            check(poster['inputSha256']==hashlib.sha256((directory/'data/posts.json').read_bytes()).hexdigest(), 'Poster built from stale input')
            image=(directory/'screenshots.png').read_bytes()
            validate_rgb_png(image,1744,960)
            check(len(image)<=240*1024, 'Poster exceeds Vanish media budget')
            check((directory/'poster.html').exists(), 'Poster HTML absent')
        except (ValueError, RuntimeError, KeyError, OSError) as exc:
            errors.append(f'Poster publication validation: {exc}')
    result = {'ok': not errors, 'errors': errors, 'warnings': warnings, 'accounts': len(expected), 'selected': len(posts), 'channels': channel_counts, 'windowStart': data['windowStart'], 'fetchStartedAt': data['fetchStartedAt']}
    (directory / 'data/mobile-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--publication', action='store_true')
    args=parser.parse_args()
    result = validate(args.directory, args.publication)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(0 if result['ok'] else 1)
