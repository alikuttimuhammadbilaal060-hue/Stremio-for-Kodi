"""Durable result acknowledgements; retry reporting, never the command itself."""
import json
import os
import re
import tempfile
from pathlib import Path

MAX_PENDING=100


class ResultOutbox:
    def __init__(self,path):self.path=Path(path)

    def document(self):
        if not self.path.exists():return {'schema':1,'results':{},'started':{}}
        if self.path.stat().st_size>1024*1024:raise ValueError('Command result outbox exceeds limit')
        document=json.loads(self.path.read_text())
        if document.get('schema')!=1 or not isinstance(document.get('results'),dict) or not isinstance(document.get('started',{}),dict):
            raise ValueError('Invalid command result outbox')
        document.setdefault('started',{})
        return document

    def read(self):return self.document()['results']

    def interrupted(self):return self.document()['started']

    def save(self,results,started=None):
        if started is None:started=self.interrupted()
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(mode='w',dir=self.path.parent,prefix='.results-',delete=False) as output:
                temporary=Path(output.name)
                json.dump({'schema':1,'results':results,'started':started},output)
                output.flush();os.fsync(output.fileno())
            os.replace(temporary,self.path)
        finally:
            if temporary and temporary.exists():temporary.unlink()

    def enqueue(self,identity,payload):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',identity):raise ValueError('Invalid command identity')
        document=self.document();results=document['results'];started=document['started']
        if identity not in results and len(results)>=MAX_PENDING:raise ValueError('Command result outbox is full')
        if len(json.dumps(payload).encode())>8192:raise ValueError('Command result exceeds limit')
        results[identity]=payload;started.pop(identity,None)
        self.save(results,started)

    def begin(self,identity,action):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',identity):raise ValueError('Invalid command identity')
        document=self.document();results=document['results'];started=document['started']
        if identity in results or identity in started:raise ValueError('Command already has a local execution record')
        if len(results)+len(started)>=MAX_PENDING:raise ValueError('Command result outbox is full')
        started[identity]=str(action)[:40]
        self.save(results,started)

    def flush(self,sender):
        results=self.read();confirmed=0
        for identity,payload in list(results.items()):
            try:
                response=sender(identity,payload)
                if not isinstance(response,dict) or response.get('ok') is not True:break
            except Exception:break
            del results[identity];self.save(results);confirmed+=1
        return confirmed
