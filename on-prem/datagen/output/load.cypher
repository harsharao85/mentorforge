// MentorForge — Neo4j LOAD CSV script
// Copy all CSV files into Neo4j's import directory, then run:
//   cypher-shell -u neo4j -p <password> -f load.cypher
// or paste into Neo4j Browser.

// ── Constraints ────────────────────────────────────────────────────
CREATE CONSTRAINT person_id     IF NOT EXISTS FOR (n:Person)        REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT role_id       IF NOT EXISTS FOR (n:Role)          REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT team_id       IF NOT EXISTS FOR (n:Team)          REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT practice_id   IF NOT EXISTS FOR (n:Practice)      REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT location_id   IF NOT EXISTS FOR (n:Location)      REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT engagement_id IF NOT EXISTS FOR (n:Engagement)    REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT community_id  IF NOT EXISTS FOR (n:Community)     REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT journey_id    IF NOT EXISTS FOR (n:Journey)       REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT stage_id      IF NOT EXISTS FOR (n:Stage)         REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT task_id       IF NOT EXISTS FOR (n:Task)          REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT milestone_id  IF NOT EXISTS FOR (n:Milestone)     REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT skill_id      IF NOT EXISTS FOR (n:Skill)         REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT interest_id   IF NOT EXISTS FOR (n:Interest)      REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT pulse_id      IF NOT EXISTS FOR (n:PulseResponse) REQUIRE n.id IS UNIQUE;

// ── Nodes ────────────────────────────────────────────────────────────
LOAD CSV WITH HEADERS FROM 'file:///nodes_Person.csv' AS row
CREATE (:Person {id:row.id, name:row.name, email:row.email, status:row.status, start_date:row.start_date, level:row.level, ladder_level:row.ladder_level, location_id:row.location_id, timezone:row.timezone, languages:row.languages, tenure_months:toInteger(row.tenure_months), employment_type:row.employment_type, discoverable:row.discoverable='True', networking_opt_in:row.networking_opt_in='True', work_style:row.work_style, bio:row.bio});

LOAD CSV WITH HEADERS FROM 'file:///nodes_Role.csv' AS row
CREATE (:Role {id:row.id, title:row.title, role_family:row.role_family, ladder_level:row.ladder_level});

LOAD CSV WITH HEADERS FROM 'file:///nodes_Team.csv' AS row
CREATE (:Team {id:row.id, name:row.name, function:row.function});

LOAD CSV WITH HEADERS FROM 'file:///nodes_Practice.csv' AS row
CREATE (:Practice {id:row.id, name:row.name});

LOAD CSV WITH HEADERS FROM 'file:///nodes_Location.csv' AS row
CREATE (:Location {id:row.id, office:row.office, geo:row.geo, timezone:row.timezone});

LOAD CSV WITH HEADERS FROM 'file:///nodes_Engagement.csv' AS row
CREATE (:Engagement {id:row.id, client:row.client, industry:row.industry, status:row.status});

LOAD CSV WITH HEADERS FROM 'file:///nodes_Community.csv' AS row
CREATE (:Community {id:row.id, type:row.type, name:row.name, blurb:row.blurb});

LOAD CSV WITH HEADERS FROM 'file:///nodes_Journey.csv' AS row
CREATE (:Journey {id:row.id, type:row.type, role_scope:row.role_scope, practice_scope:row.practice_scope});

LOAD CSV WITH HEADERS FROM 'file:///nodes_Stage.csv' AS row
CREATE (:Stage {id:row.id, name:row.name, journey_id:row.journey_id, offset_days_start:toInteger(row.offset_days_start), offset_days_end:toInteger(row.offset_days_end)});

LOAD CSV WITH HEADERS FROM 'file:///nodes_Task.csv' AS row
CREATE (:Task {id:row.id, title:row.title, category:row.category, owner_role:row.owner_role, due_offset_days:toInteger(row.due_offset_days), mandatory:row.mandatory='True'});

LOAD CSV WITH HEADERS FROM 'file:///nodes_Milestone.csv' AS row
CREATE (:Milestone {id:row.id, name:row.name, description:row.description});

LOAD CSV WITH HEADERS FROM 'file:///nodes_Skill.csv' AS row
CREATE (:Skill {id:row.id, name:row.name, category:row.category});

LOAD CSV WITH HEADERS FROM 'file:///nodes_Interest.csv' AS row
CREATE (:Interest {id:row.id, name:row.name});

LOAD CSV WITH HEADERS FROM 'file:///nodes_PulseResponse.csv' AS row
CREATE (:PulseResponse {id:row.id, moment:row.moment, score:toInteger(row.score), comment:row.comment});

// ── Relationships ───────────────────────────────────────────────────
LOAD CSV WITH HEADERS FROM 'file:///rels_reports_to.csv' AS row
MATCH (a:Person {id:row.from_id}), (b:Person {id:row.to_id})
CREATE (a)-[:REPORTS_TO]->(b);

LOAD CSV WITH HEADERS FROM 'file:///rels_member_of.csv' AS row
MATCH (a:Person {id:row.from_id}), (b:Team {id:row.to_id})
CREATE (a)-[:MEMBER_OF]->(b);

LOAD CSV WITH HEADERS FROM 'file:///rels_part_of.csv' AS row
MATCH (a:Team {id:row.from_id}), (b:Practice {id:row.to_id})
CREATE (a)-[:PART_OF]->(b);

LOAD CSV WITH HEADERS FROM 'file:///rels_has_role.csv' AS row
MATCH (a:Person {id:row.from_id}), (b:Role {id:row.to_id})
CREATE (a)-[:HAS_ROLE]->(b);

LOAD CSV WITH HEADERS FROM 'file:///rels_based_at.csv' AS row
MATCH (a:Person {id:row.from_id}), (b:Location {id:row.to_id})
CREATE (a)-[:BASED_AT]->(b);

LOAD CSV WITH HEADERS FROM 'file:///rels_staffed_on.csv' AS row
MATCH (a:Person {id:row.from_id}), (b:Engagement {id:row.to_id})
CREATE (a)-[:STAFFED_ON]->(b);

LOAD CSV WITH HEADERS FROM 'file:///rels_leads_team.csv' AS row
MATCH (a:Person {id:row.from_id}), (b:Team {id:row.to_id})
CREATE (a)-[:LEADS]->(b);

LOAD CSV WITH HEADERS FROM 'file:///rels_leads_practice.csv' AS row
MATCH (a:Person {id:row.from_id}), (b:Practice {id:row.to_id})
CREATE (a)-[:LEADS]->(b);

LOAD CSV WITH HEADERS FROM 'file:///rels_leads_engagement.csv' AS row
MATCH (a:Person {id:row.from_id}), (b:Engagement {id:row.to_id})
CREATE (a)-[:LEADS]->(b);

LOAD CSV WITH HEADERS FROM 'file:///rels_buddy_of.csv' AS row
MATCH (a:Person {id:row.from_id}), (b:Person {id:row.to_id})
CREATE (a)-[:BUDDY_OF]->(b);

LOAD CSV WITH HEADERS FROM 'file:///rels_mentor_of.csv' AS row
MATCH (a:Person {id:row.from_id}), (b:Person {id:row.to_id})
CREATE (a)-[:MENTOR_OF]->(b);

LOAD CSV WITH HEADERS FROM 'file:///rels_cohort_with.csv' AS row
MATCH (a:Person {id:row.from_id}), (b:Person {id:row.to_id})
CREATE (a)-[:COHORT_WITH]->(b);

LOAD CSV WITH HEADERS FROM 'file:///rels_member_of_community.csv' AS row
MATCH (a:Person {id:row.from_id}), (b:Community {id:row.to_id})
CREATE (a)-[:MEMBER_OF_COMMUNITY]->(b);

LOAD CSV WITH HEADERS FROM 'file:///rels_expert_in.csv' AS row
MATCH (a:Person {id:row.from_id}), (b:Skill {id:row.to_id})
CREATE (a)-[:EXPERT_IN]->(b);

LOAD CSV WITH HEADERS FROM 'file:///rels_ask_me_about.csv' AS row
MATCH (a:Person {id:row.from_id}), (b:Skill {id:row.to_id})
CREATE (a)-[:ASK_ME_ABOUT]->(b);

LOAD CSV WITH HEADERS FROM 'file:///rels_interested_in.csv' AS row
MATCH (a:Person {id:row.from_id}), (b:Interest {id:row.to_id})
CREATE (a)-[:INTERESTED_IN]->(b);

LOAD CSV WITH HEADERS FROM 'file:///rels_assigned_journey.csv' AS row
MATCH (a:Person {id:row.from_id}), (b:Journey {id:row.to_id})
CREATE (a)-[:ASSIGNED_JOURNEY]->(b);

LOAD CSV WITH HEADERS FROM 'file:///rels_has_stage.csv' AS row
MATCH (a:Journey {id:row.from_id}), (b:Stage {id:row.to_id})
CREATE (a)-[:HAS_STAGE]->(b);

LOAD CSV WITH HEADERS FROM 'file:///rels_includes_task.csv' AS row
MATCH (a:Stage {id:row.from_id}), (b:Task {id:row.to_id})
CREATE (a)-[:INCLUDES_TASK]->(b);

LOAD CSV WITH HEADERS FROM 'file:///rels_reaches.csv' AS row
MATCH (a:Person {id:row.from_id}), (b:Milestone {id:row.to_id})
CREATE (a)-[:REACHES]->(b);

LOAD CSV WITH HEADERS FROM 'file:///rels_responded.csv' AS row
MATCH (a:Person {id:row.from_id}), (b:PulseResponse {id:row.to_id})
CREATE (a)-[:RESPONDED]->(b);

LOAD CSV WITH HEADERS FROM 'file:///rels_responsible_for.csv' AS row
MATCH (t:Task {id:row.from_id}), (p:Person {id:row.to_id})
CREATE (t)-[:RESPONSIBLE_FOR {new_hire_id:row.new_hire_id}]->(p);

LOAD CSV WITH HEADERS FROM 'file:///rels_completed.csv' AS row
MATCH (p:Person {id:row.from_id}), (t:Task {id:row.to_id})
CREATE (p)-[:COMPLETED {status:row.status, timestamp:row.timestamp}]->(t);

LOAD CSV WITH HEADERS FROM 'file:///rels_collaborates_with.csv' AS row
MATCH (a:Person {id:row.from_id}), (b:Person {id:row.to_id})
CREATE (a)-[:COLLABORATES_WITH {source:row.source, is_derived:row.is_derived='True'}]->(b);

// ── Verification ─────────────────────────────────────────────────────
// Run these to confirm expected counts:
// MATCH (n:Person)   RETURN count(n) AS persons;          // ~400
// MATCH (n:Task)     RETURN count(n) AS tasks;
// MATCH ()-[:REPORTS_TO]->() RETURN count(*) AS reports_to;
// MATCH (p:Person {status:'onboarding'}) RETURN p.name, p.start_date LIMIT 5;
