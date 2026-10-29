import org.apache.hop.core.HopEnvironment;
import org.apache.hop.core.variables.Variables;
import org.apache.hop.metadata.serializer.json.JsonMetadataProvider;
import org.apache.hop.pipeline.PipelineMeta;
import org.apache.hop.workflow.WorkflowMeta;

/** Metadata ONLY. Never instantiate an engine, call getFields or query a database. */
public class ValidatePipeline {
 public static void main(String[] args) throws Exception {
  HopEnvironment.init();
  var vars = new Variables();
  vars.setVariable("PROJECT_HOME", args[0]);
  var provider = new JsonMetadataProvider();
  provider.setBaseFolder(args[0]+"/metadata");
  for (String file : new String[]{"curated_to_fact_serving_batch", "ack_committed_mart_batch"}) {
   var p = new PipelineMeta(args[0]+"/pipelines/mart/"+file+".hpl",provider,vars);
   int expected = file.startsWith("curated") ? 3 : 4;
   if(p.nrTransforms()!=expected || p.nrPipelineHops()!=expected-1) throw new IllegalStateException("Topology");
   for(var t:p.getTransforms()) {
    var meta=t.getTransform();
    var cls=meta.getClass();
    if(cls.getName().contains(".missing.")) throw new IllegalStateException("Missing plugin");
    if(cls.getSimpleName().equals("TableInputMeta")) {
     var connection=(String)cls.getMethod("getConnection").invoke(meta);
     if(p.findDatabase(connection,vars)==null) throw new IllegalStateException("Missing connection: "+connection);
     var sql=(String)cls.getMethod("getSql").invoke(meta);
     if(sql.contains("?") && !(Boolean)cls.getMethod("isExecuteEachInputRow").invoke(meta)) throw new IllegalStateException("Unbound parameter");
    }
    System.out.println(file+": "+t.getName()+" => "+cls.getSimpleName());
   }
  }
  var w=new WorkflowMeta(vars,args[0]+"/workflows/mart/curated_to_serving.hwf",provider);
  if(w.nrActions()!=3 || w.nrWorkflowHops()!=2 || w.getStart()==null) throw new IllegalStateException("Workflow topology/start");
  for(int i=0;i<w.nrActions();i++) {
   var a=w.getAction(i);
   if(a.getAction().getClass().getName().contains(".missing.")) throw new IllegalStateException("Missing action");
   System.out.println("Workflow: "+a.getName()+" => "+a.getAction().getClass().getSimpleName());
  }
  System.out.println("PASS: workflow, both pipelines, plugins and connection metadata loaded. No database connection or execution.");
  HopEnvironment.shutdown();
 }
}
