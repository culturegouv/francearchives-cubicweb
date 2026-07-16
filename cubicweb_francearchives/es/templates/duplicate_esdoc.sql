DROP TABLE IF EXISTS tmp_cw_esdocument;

begin;

-- Create a table to save the last updated IR eid
CREATE TABLE tmp_last_esdocument (last integer);
INSERT INTO  tmp_last_esdocument VALUES (0);

-- Save a copy of cw_esdocument table
-- CREATE TABLE tmp_cw_esdocument AS SELECT * FROM cw_esdocument;
CREATE TABLE tmp_cw_esdocument (LIKE cw_esdocument INCLUDING ALL);

INSERT INTO tmp_cw_esdocument(cw_eid, cw_doc, cw_entity) SELECT cw_eid,  cw_doc, cw_entity FROM cw_esdocument;

commit ;
