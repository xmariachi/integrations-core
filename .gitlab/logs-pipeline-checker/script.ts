import * as fs from 'fs';
import * as ts from "typescript";
import { parse, TSESTreeOptions } from "@typescript-eslint/typescript-estree";

const source = fs.readFileSync('web-ui/javascript/datadog/logs/lib/integrations/integrations.ts','utf8');
const options: TSESTreeOptions = {comment: false, jsx: false};
const program = parse(source, options).body;

// Remove everything from the program except variable declaration of type const where the variable is named LOG_INTEGRATIONS
var filteredProgram = program.filter(x => x['type'] === 'VariableDeclaration' && x['kind'] === 'const' && x['declarations'][0]['id']['name'] == 'LOG_INTEGRATIONS');

if(filteredProgram.length != 1) {
    // raise exc
}

const logIntegrationVarLocation = filteredProgram[0]['range'];
var logIntegrationDeclaration = source.slice(logIntegrationVarLocation[0], logIntegrationVarLocation[1]);

logIntegrationDeclaration += "\nLOG_INTEGRATIONS;\n"

const LOG_INTEGRATIONS = eval(ts.transpile(logIntegrationDeclaration))

console.log(JSON.stringify(LOG_INTEGRATIONS));
