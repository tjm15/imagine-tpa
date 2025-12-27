import React, { useEffect } from 'react';
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
    height?: number;
}

const TraceGraph: React.FC<TraceGraphProps> = ({ nodes: initialNodes, edges: initialEdges, height = 280 }) => {
    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

    useEffect(() => {
        setNodes(initialNodes);
    }, [initialNodes, setNodes]);

    useEffect(() => {
        setEdges(initialEdges);
    }, [initialEdges, setEdges]);

    return (
        <div className="w-full border border-stone-200 rounded-lg" style={{ height }}>
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
