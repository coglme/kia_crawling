from contextlib import contextmanager
from pathlib import Path
import errno

class AlreadyRunning(BlockingIOError):
    pass

def acquire(operation):
    try:
        operation()
    except OSError as exc:
        if exc.errno in (errno.EACCES,errno.EAGAIN,errno.EDEADLK):
            raise AlreadyRunning('Job lock already held') from exc
        raise

@contextmanager
def job_lock(database):
    """OS lock, released even on process death; never delete the lock file."""
    path=Path(database+'.lock'); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as handle:
        handle.seek(0,2)
        if handle.tell()==0:
            handle.write(b'0'); handle.flush()
        handle.seek(0)
        try:
            import fcntl
        except ImportError:
            import msvcrt
            acquire(lambda: msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1))
            try:
                yield
            finally:
                handle.seek(0); msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
        else:
            acquire(lambda: fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB))
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
