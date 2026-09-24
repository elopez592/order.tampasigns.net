"""Compare the full suite with the unmodified release; do not hide new failures."""
import concurrent.futures
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

root=Path.cwd()
base=Path(tempfile.mkdtemp(prefix='wrap-baseline-'))/'repo'
subprocess.run(['git','worktree','add','--detach',str(base),'b5ba4d9bdf82d88b31d1ac027dea7f64e9660be8'],check=True)

def run(folder):
    report=folder/'wrap-regression-results.xml'
    result=subprocess.run(['python','-m','pytest','-q','--junitxml='+str(report)],cwd=folder,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=300)
    if result.returncode not in (0,1) or not report.exists():
        raise RuntimeError(result.stdout)
    tests=ET.parse(report).getroot().findall('.//testcase')
    failures={node.get('classname','')+'::'+node.get('name','') for node in tests if node.find('failure') is not None or node.find('error') is not None}
    return len(tests),failures,result.stdout
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
    baseline=executor.submit(run,base)
    candidate=executor.submit(run,root)
    old_count,old_failures,old_output=baseline.result()
    count,failures,output=candidate.result()
print('BASELINE:',old_count,'tests;',len(old_failures),'existing failures')
print('CANDIDATE:',count,'tests;',len(failures),'failures')
print('Existing failing checks:',sorted(old_failures))
if failures-old_failures or count<old_count:
    print(output)
    raise RuntimeError('New regression failures or missing test coverage: '+repr(failures-old_failures))
print('PASS: no new regressions relative to the unchanged production release.')
