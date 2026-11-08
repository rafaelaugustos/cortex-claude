import subprocess
import sys


def test_repeated_health_archive_and_backups_fit_low_file_limit(tmp_path):
    script = r'''
import gc,json,resource,sys,threading
from pathlib import Path
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from cortex_claude.learning.store import LearningStore
from cortex_claude.storage.database import StorageManager
from cortex_claude.web import server as web
home=Path(sys.argv[1]);home.mkdir(exist_ok=True)
(home/'config.json').write_text('{"reliability":{"auto_backup":false,"backup_keep":2}}')
with LearningStore(home): pass
storage=StorageManager(home);storage.get_database('global');storage.close_all()
web.CORTEX_HOME=home
server=ThreadingHTTPServer(('127.0.0.1',0),web.CortexHandler)
server.daemon_threads=True
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
gc.collect();gc.disable()
soft,hard=resource.getrlimit(resource.RLIMIT_NOFILE)
resource.setrlimit(resource.RLIMIT_NOFILE,(min(64,soft),hard))
try:
 for index in range(45):
  for method,path in [('GET','/api/health'),('GET','/api/overview')]+([('POST','/api/recovery/backup')] if index%10==0 else []):
   connection=HTTPConnection(*server.server_address,timeout=5)
   connection.request(method,path)
   response=connection.getresponse();data=json.loads(response.read());connection.close()
   assert response.status==200,(index,path,data)
   if path=='/api/health': assert all(db['readable'] for db in data['databases']),data['issues']
finally:
 server.shutdown();server.server_close();thread.join(5)
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path / 'memory')], capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
