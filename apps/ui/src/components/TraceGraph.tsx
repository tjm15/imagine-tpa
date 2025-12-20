import React, { useMemo } from 'react';
import {
    ReactFlow,
    Background,
    Controls,
    MiniMap,
    useNodesState,
    useEdgesState,
    Node,
    Edge
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

interface TraceGraphProps {
    nodes: Node[];
    edges: Edge[];
}

const TraceGraph: React.FC<TraceGraphProps> = ({ nodes: initialNodes, edges: initialEdges }) => {
    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

    return (
        <div className="w-full h-full min-h-[500px] border border-stone-200 rounded-lg">
            <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                fitView
            >
                <Background />
                <Controls />
                <MiniMap />
            </ReactFlow>
        </div>
    );
};

export default TraceGraph;
