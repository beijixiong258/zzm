import {renderToStaticMarkup} from "react-dom/server";
import {afterEach,describe,expect,it,vi} from "vitest";
import {api} from "../src/api";
import {canAccessRoute,readRoute,routeHash} from "../src/routes";
import CourseActions,{courseFields,courseReadbackMatches} from "../src/CourseActions";
import Home from "../src/Home";
import type {CourseDetails,User} from "../src/types";
const course:CourseDetails={id:"synthetic-course /1",code:"S8",title:"Synthetic seminar",description:"Original description",student_count:1,admin_count:0,teacher_count:1,join_code:"synthetic-invitation",published_version_id:"v1",published_version_number:1,has_unpublished_changes:false,trashed_at:null,session_count:2,material_count:3,enrollment_count:1};
const teacher:User={id:"teacher",name:"Synthetic teacher",email:"teacher@example.invalid",role:"teacher"};
const noop=()=>{};const refresh=async()=>{};
afterEach(()=>vi.unstubAllGlobals());
describe("Stage8 course lifecycle frontend contract",()=>{
 it("only editable metadata is sent, not relational identity or access code",()=>{expect(courseFields(course)).toEqual({code:"S8",title:"Synthetic seminar",description:"Original description"});expect(courseFields(course)).not.toHaveProperty("id");expect(courseFields(course)).not.toHaveProperty("join_code");});
 it("independent readback requires exact ID, active state and all submitted values",()=>{const f=courseFields(course);expect(courseReadbackMatches(course,course.id,f)).toBe(true);expect(courseReadbackMatches({...course,title:"Different"},course.id,f)).toBe(false);expect(courseReadbackMatches({...course,trashed_at:"2026-10-08T01:00:00Z"},course.id,f)).toBe(false);expect(courseReadbackMatches({...course,id:"another"},course.id,f)).toBe(false);});
 it("preserves literal code and description whitespace instead of silently repairing values",()=>{const f={code:" A / 1 ",title:"Name",description:"Line one\n\nLine two"};expect(courseReadbackMatches({...course,...f},course.id,f)).toBe(true);expect(courseFields({...course,...f})).toEqual(f);});
 it.each(["student","teacher","admin"] as const)("limits trash route by role %s",role=>{expect(canAccessRoute(role,"course-trash")).toBe(role!=="student");});
 it("roundtrips trash route and keeps malformed paths safe",()=>{expect(readRoute("#/course-trash").page).toBe("course-trash");expect(routeHash({page:"course-trash"})).toBe("/course-trash");expect(readRoute("#/course-materials/%zz")).toEqual({page:"home"});});
 it("course actions are a labelled disclosure with edit and recoverable trash, never hard deletion",()=>{const html=renderToStaticMarkup(<CourseActions course={course} onChanged={refresh}/>);expect(html).toContain("Course actions");expect(html).toContain("Edit course");expect(html).toContain("Move to trash");expect(html).not.toMatch(/Permanently delete|Delete forever/);expect(html).not.toContain('open=""');});
 it("blocks metadata actions while an unrelated inline creation form owns the target",()=>{const html=renderToStaticMarkup(<CourseActions course={course} disabled onChanged={refresh}/>);expect(html).toContain('aria-disabled="true"');expect(html).toContain('tabindex="-1"');expect(html.match(/disabled=""/g)?.length).toBe(2);});
 it("staff can reach Trash even with no active courses left",()=>{const html=renderToStaticMarkup(<Home user={teacher} courses={[]} sessionMap={{}} loading={false} history={false} onOpen={noop} onPreview={noop} onRefresh={refresh} onRoster={noop} onVersions={noop} onTrash={noop}/>);expect(html).toContain("Trash");expect(html).toContain("Create course");});
 it("student Course Home has no course-edit or trash affordance",()=>{const html=renderToStaticMarkup(<Home user={{...teacher,role:"student"}} courses={[course]} sessionMap={{}} loading={false} history={false} onOpen={noop} onPreview={noop} onRefresh={refresh} onRoster={noop} onVersions={noop} onTrash={noop}/>);expect(html).not.toContain("Course actions");expect(html).not.toContain("Move to trash");expect(html).not.toContain(">Trash<");});
 it("uses real PATCH/POST/GET endpoints with encoded literal identifiers",async()=>{
  const fetch=vi.fn(async()=>new Response("{}",{headers:{"Content-Type":"application/json"}}));vi.stubGlobal("fetch",fetch);
  await api.courseDetails(course.id);await api.updateCourse(course.id,{title:"Updated",description:"Text"});await api.trashCourse(course.id);await api.restoreCourse(course.id);await api.courseTrash();
  const calls=fetch.mock.calls as unknown as [string,RequestInit][];
  expect(calls.map(c=>c[0])).toEqual(["/api/courses/synthetic-course%20%2F1","/api/courses/synthetic-course%20%2F1","/api/courses/synthetic-course%20%2F1/trash","/api/courses/synthetic-course%20%2F1/restore","/api/courses/trash"]);
  expect(calls[1][1].method).toBe("PATCH");expect(JSON.parse(calls[1][1].body as string)).toEqual({title:"Updated",description:"Text"});expect(calls[2][1].method).toBe("POST");expect(calls[3][1].method).toBe("POST");expect(JSON.parse(calls[2][1].body as string)).toEqual({});
 });
});
