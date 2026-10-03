"""Explicit owned catalogue fixtures; never activate legacy files implicitly."""
from filehub.automation.models import RuleSet
from filehub.rulefiles.migration import legacy_package
from filehub.rules import discover_projects
from filehub.templates import TemplateLibrary


def install_rules(service, *rules):
    package,bindings,ids=legacy_package(RuleSet(rules),service.config,TemplateLibrary(),
        discover_projects(service.config.sync_root) if service.config.sync_root else {})
    snapshot=service.catalog.load()
    def change(doc):
        doc['packages']=[dict(package=package.to_document(),source=None,bindings={k:str(v) for k,v in bindings.items()},
                              runtime_ids=dict(ids),enabled=[r.id for r in rules if r.enabled])]
        doc['compatibility_selection']=package.id if package.compatibility else None
        doc['compatibility_permissions']=['manual_archive'] if package.compatibility else []
    return service.catalog._mutate(snapshot.revision,change)


def install_archive(service, *, library=None, permissions=frozenset({'manual_archive'})):
    package,bindings,ids=legacy_package(RuleSet(),service.config,library or TemplateLibrary(),discover_projects(service.config.sync_root))
    snapshot=service.catalog.load()
    data=__import__('filehub.rulefiles',fromlist=['encode_package']).encode_package(package)
    if package.id in snapshot.packages:
        snapshot=service.catalog.replace_package(package.id,data,expected_revision=snapshot.revision)
    else:
        snapshot=service.catalog.import_package(data,expected_revision=snapshot.revision)
    snapshot=service.catalog.bind(package.id,bindings,expected_revision=snapshot.revision)
    return service.catalog.set_compatibility(package.id,permissions,expected_revision=snapshot.revision)


def set_archive_permissions(service,permissions):
    snapshot=service.catalog.load()
    return service.catalog.set_compatibility('legacy-import',frozenset(permissions),expected_revision=snapshot.revision)
