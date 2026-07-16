DROP TABLE IF EXISTS public.tmp_findingaid_es;

begin;

-- Create tmp_findingaid_es


CREATE TABLE public.tmp_findingaid_es AS
SELECT X.cw_eid, _S.cw_name
FROM public.cw_FindingAid AS X, cw_State AS _S, in_state_relation AS in_state
WHERE in_state.eid_from=X.cw_eid AND in_state.eid_to=_S.cw_eid;

CREATE INDEX tmp_fi_eid_idx ON tmp_findingaid_es(cw_eid);
commit ;
