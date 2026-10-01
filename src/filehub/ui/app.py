"""Phase A application factories; runtime integration remains injectable."""
from pathlib import Path
from uuid import uuid4
from filehub.config import Config, ConfigStore
from filehub.service import FileHubService

def create_demo(base_dir):
    """Create only uniquely owned demo directories under the supplied app state."""
    base=Path(base_dir)/'demo'/uuid4().hex
    sync=base/'同步空间';watch=base/'示例下载'
    (sync/'1_工作'/'项目'/'261001_DEMO_示例项目').mkdir(parents=True)
    watch.mkdir();source=watch/'镜头素材.png';source.write_bytes(b'FileHub isolated demo sample')
    config=Config(sync_root=sync,watch_roots=(watch,),paused=True,global_jobs=False)
    store=ConfigStore(base/'state');store.save(config)
    return FileHubService(config,base/'state'),store,(source,)
