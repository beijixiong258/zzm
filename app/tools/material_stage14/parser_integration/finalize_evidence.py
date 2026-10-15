"""Aggregate actual regression, package and CPU evidence for parent handoff."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

APP=Path(__file__).resolve().parents[3]
OUT=APP/'artifacts/stage14/parser-integration'


def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def tests(name):
    p=OUT/name;root=ET.parse(p).getroot();suites=list(root.iter('testsuite'))
    skips=[{'name':t.attrib.get('name'),'reason':s.attrib.get('message') or s.text} for t in root.iter('testcase') for s in t.findall('skipped')]
    failures=[{'name':t.attrib.get('name'),'message':s.attrib.get('message')} for t in root.iter('testcase') for tag in ('failure','error') for s in t.findall(tag)]
    return {'file':str(p),'sha256':sha(p),'tests':sum(int(x.attrib['tests']) for x in suites),
            'failures':sum(int(x.attrib['failures']) for x in suites),'errors':sum(int(x.attrib['errors']) for x in suites),
            'skipped':sum(int(x.attrib['skipped']) for x in suites),'skip_details':skips,'failure_details':failures}


def main():
    load=lambda n:json.loads((OUT/n).read_text(encoding='utf-8'))
    backend=tests('backend-full.xml');frames=tests('frame-admission-final.xml');linux=tests('linux-parser-final.xml')
    frontend=load('frontend-tests.json');cpu=load('cpu-overlay-check.json');snapshot=load('runtime-module-snapshot.json')
    smoke=load('runtime-snapshot-linux-smoke.json');dep=load('dependency-manifest.json');readback=load('dependency-readback.json')
    pre=load('cpu-inventory.json');post=load('cpu-inventory-post.json');native=load('opencv-native-check.json')
    limits=json.loads((OUT/'linux-parser-limits.log').read_text())
    changed=['backend/aicademiya/document_bundle.py','tools/build_v2_release.py','tools/material_stage14/test_simple_material.py']
    new=sorted(p.relative_to(APP).as_posix() for p in (APP/'tools/material_stage14/parser_integration').iterdir() if p.suffix in ('.py','.md'))
    result={'scope':'source-only parser admission/package/CPU integration; no production/GPU/full semantic acceptance',
            'backend':backend,'full_frame_app_bundle_tests':frames,'linux_parser':linux,
            'linux_parser_console':'104 passed +8subtests; three separate real preallocation CLI cases passed',
            'linux_limits':{'status':limits['status'],'cases':len(limits['cases']),'model_calls':limits['model_calls']},
            'frontend':{k:frontend[k] for k in ('success','numTotalTests','numPassedTests','numFailedTests','numPendingTests')},
            'frontend_build':{'status':'passed','log':str(OUT/'frontend-build.log'),'warning':'existing >500kB chunk warning; not a failure'},
            'scoped_runtime_snapshot':{'file_count':snapshot['file_count'],'sha256':snapshot['archive_sha256'],
                                       'backend_import_returncode':snapshot['backend_import']['returncode'],
                                       'linux_cli_native_checks':len(smoke['results']),'linux_cli_native_passed':smoke['all_passed'],
                                       'not_a_final_release':True},
            'dependency_payload':{'remote_stage':readback['remote_stage'],'wheel_count':len(dep['wheels']),'model_count':len(dep['models']),
                                  'bytes':dep['payload_bytes'],'manifest_sha256':readback['files']['dependency-manifest.json']['sha256'],
                                  'requirements_sha256':readback['files']['requirements-offline.txt']['sha256'],
                                  'transport_exact_match':readback['exact_transport_match'],'installer_plan_verified':load('dependency-install-plan.json')['payload_verified'],
                                  'wheels_source':'repacked existing baseline distributions after original RECORD size/hash verification, not original publisher archives'},
            'cpu_overlay':{'status':cpu['status'],'uid':cpu['uid'],'interpreter':cpu['interpreter'],
                           'exact_groundtruth_agreement':cpu['exact_groundtruth_agreement'],'providers':cpu['independent_ocr']['actual_providers'],
                           'missing_dependencies':cpu['missing_dependencies'],'network_blocked':cpu['network_blocked'],'gpu_calls':cpu['gpu_calls'],
                           'pip_check':'No broken requirements found','native_unresolved':native['unresolved']},
            'installed_environment':{'packages_unchanged':pre['environments']['installed']['data']['packages']==post['environments']['installed']['data']['packages'],
                                     'baseline_weights_unchanged':pre['models']==post['models'],
                                     'still_missing':[n for n in ('rapidocr','omegaconf','colorlog','opencv-python') if post['environments']['installed']['data']['packages'][n] is None],
                                     'new_parser_deployed':False,'uid999_tested':False},
            'harness_failures_retained':[
                {'file':'linux-parser-full.log','cause':'CLI-only test_parser_limits.py was accidentally collected by pytest; ran it separately with absolute scratch root; no product edits'},
                {'file':'runtime-snapshot-linux-smoke-initial.json','cause':'universal-newline read_text comparison normalized Windows source CRLF; corrected test to compare exact decoded source bytes'},
                {'cause':'public dependency download timed out; owned remote pip PID123559 terminated and absence checked; no wheel/model downloaded; used verified local baseline packages'}],
            'modified_files':{p:{'bytes':(APP/p).stat().st_size,'sha256':sha(APP/p)} for p in changed},
            'created_tools':{p:{'bytes':(APP/p).stat().st_size,'sha256':sha(APP/p)} for p in new}}
    assert backend['failures']==backend['errors']==frames['failures']==frames['errors']==linux['failures']==linux['errors']==0
    assert frontend['success'] and smoke['all_passed'] and cpu['status']=='passed' and readback['exact_transport_match']
    assert result['installed_environment']['packages_unchanged'] and result['installed_environment']['baseline_weights_unchanged']
    (OUT/'verification-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'checksums.sha256').write_text(''.join(sha(p)+'  '+p.name+'\n' for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='checksums.sha256'),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('backend','full_frame_app_bundle_tests','linux_parser','frontend','dependency_payload','cpu_overlay','installed_environment')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
