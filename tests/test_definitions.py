from alpes_water_monitor.dagster_app.definitions import defs


def test_definitions_load():
    # Ensure Dagster definitions can be imported and expose assets
    graph = defs.resolve_asset_graph()
    asset_keys = {ak.to_user_string() for ak in graph.get_all_asset_keys()}
    assert asset_keys, "No assets found in Dagster definitions"
