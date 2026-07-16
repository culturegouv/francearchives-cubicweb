
DROP TABLE IF EXISTS tmp_{{etype}}_qualified;
CREATE TABLE tmp_{{ etype }}_qualified (
  eid integer PRIMARY KEY not null
);

DROP TABLE IF EXISTS tmp_{{ etype }}_not_qualified;
CREATE TABLE tmp_{{ etype }}_not_qualified (
  eid integer PRIMARY KEY not null
);


begin;

-- Insert {{ Etype }} eids into tmp_{{ etype }}_qualified in {{ schema }} schema"""

INSERT INTO tmp_{{ etype }}_qualified
SELECT DISTINCT _F.cw_eid
FROM cw_LocationAuthority AS _X, cw_Geogname AS _INDEX,
     {% if schema %}{{ schema }}.{% endif -%}cw_{{ etype }} AS _F,
     index_relation AS rel_index0
WHERE _X.cw_quality=true AND
      _INDEX.cw_authority=_X.cw_eid AND
      rel_index0.eid_from=_INDEX.cw_eid AND
      rel_index0.eid_to=_F.cw_eid;

INSERT INTO tmp_{{ etype }}_qualified
SELECT DISTINCT _F.cw_eid
FROM cw_AgentAuthority AS _X, cw_AgentName AS _INDEX,
     {% if schema %}{{ schema }}.{% endif -%}cw_{{ etype }} AS _F,
     index_relation AS rel_index0
WHERE _X.cw_quality=true AND
      _INDEX.cw_authority=_X.cw_eid AND
      rel_index0.eid_from=_INDEX.cw_eid AND
      rel_index0.eid_to=_F.cw_eid
ON CONFLICT (eid) DO NOTHING;

INSERT INTO tmp_{{ etype }}_qualified
SELECT DISTINCT _F.cw_eid
FROM cw_SubjectAuthority AS _X, cw_Subject AS _INDEX,
     {% if schema %}{{ schema }}.{% endif -%}cw_{{ etype }} AS _F,
     index_relation AS rel_index0
WHERE _X.cw_quality=true AND
      _INDEX.cw_authority=_X.cw_eid AND
      rel_index0.eid_from=_INDEX.cw_eid AND
      rel_index0.eid_to=_F.cw_eid
ON CONFLICT (eid) DO NOTHING;

{%- if etype == 'findingaid' %}
INSERT INTO tmp_{{ etype }}_qualified
SELECT DISTINCT _X.cw_eid
FROM {% if schema %}{{ schema }}.{% endif -%}cw_{{ etype }} as _X,
     tmp_facomponent_qualified as _T,
     {% if schema %}{{ schema }}.{% endif -%}cw_FAComponent AS _F
WHERE _X.cw_eid=_F.cw_finding_aid AND
      _F.cw_eid=_T.eid
ON CONFLICT (eid) DO NOTHING;
{% endif %}

{%- if generate_not_qualified %}
INSERT INTO tmp_{{ etype }}_not_qualified
SELECT DISTINCT _F.cw_eid
FROM {% if schema %}{{ schema }}.{% endif -%}cw_{{ etype }} AS _F
WHERE NOT EXISTS(SELECT eid
      FROM tmp_{{ etype }}_qualified
      WHERE _F.cw_eid = tmp_{{ etype }}_qualified.eid);
{% endif %}

commit ;
