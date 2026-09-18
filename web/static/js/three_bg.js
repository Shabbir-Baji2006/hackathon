document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('bgCanvas');
    if (!canvas) return;

    // Set up Scene, Camera, and Renderer
    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x0a0a0a, 0.001); // Subtle depth fading

    const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.z = 250;

    const renderer = new THREE.WebGLRenderer({
        canvas: canvas,
        alpha: true,
        antialias: true
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2)); // Cap pixel ratio for performance
    renderer.setSize(window.innerWidth, window.innerHeight);

    // ==========================================
    // Procedural Glowing Texture for Particles
    // ==========================================
    const createGlowTexture = () => {
        const size = 64;
        const texCanvas = document.createElement('canvas');
        texCanvas.width = size;
        texCanvas.height = size;
        const context = texCanvas.getContext('2d');

        // Draw a radial gradient
        const gradient = context.createRadialGradient(size/2, size/2, 0, size/2, size/2, size/2);
        gradient.addColorStop(0, 'rgba(255, 255, 255, 1)');
        gradient.addColorStop(0.2, 'rgba(37, 99, 235, 1)'); // Deep blue
        gradient.addColorStop(0.5, 'rgba(37, 99, 235, 0.2)');
        gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');

        context.fillStyle = gradient;
        context.fillRect(0, 0, size, size);

        const texture = new THREE.CanvasTexture(texCanvas);
        return texture;
    };

    // ==========================================
    // Network Nodes (Particles) Setup
    // ==========================================
    const particlesCount = window.innerWidth > 768 ? 400 : 200; // Less on mobile
    const particlesGeometry = new THREE.BufferGeometry();
    const posArray = new Float32Array(particlesCount * 3);
    const originArray = new Float32Array(particlesCount * 3); // Store original positions for drifting
    const phaseArray = new Float32Array(particlesCount * 3);  // Random phases for organic movement

    const spread = 600;

    for (let i = 0; i < particlesCount * 3; i++) {
        const val = (Math.random() - 0.5) * spread;
        posArray[i] = val;
        originArray[i] = val;
        phaseArray[i] = Math.random() * Math.PI * 2;
    }

    particlesGeometry.setAttribute('position', new THREE.BufferAttribute(posArray, 3));
    particlesGeometry.setAttribute('origin', new THREE.BufferAttribute(originArray, 3));
    particlesGeometry.setAttribute('phase', new THREE.BufferAttribute(phaseArray, 3));

    const particlesMaterial = new THREE.PointsMaterial({
        size: 8,
        map: createGlowTexture(),
        transparent: true,
        opacity: 0.8,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        color: 0xffffff
    });

    const particlesMesh = new THREE.Points(particlesGeometry, particlesMaterial);
    scene.add(particlesMesh);

    // ==========================================
    // Dynamic Connection Lines Setup
    // ==========================================
    const maxConnections = particlesCount * 10; 
    const linesGeometry = new THREE.BufferGeometry();
    
    // 2 vertices per line (start and end), 3 coordinates per vertex
    const linePositions = new Float32Array(maxConnections * 2 * 3);
    const lineColors = new Float32Array(maxConnections * 2 * 3); // For fading lines based on distance
    
    linesGeometry.setAttribute('position', new THREE.BufferAttribute(linePositions, 3).setUsage(THREE.DynamicDrawUsage));
    linesGeometry.setAttribute('color', new THREE.BufferAttribute(lineColors, 3).setUsage(THREE.DynamicDrawUsage));

    const linesMaterial = new THREE.LineBasicMaterial({
        vertexColors: true,
        transparent: true,
        opacity: 0.35, // Low opacity for high-end feel
        blending: THREE.AdditiveBlending,
        depthWrite: false
    });

    const linesMesh = new THREE.LineSegments(linesGeometry, linesMaterial);
    scene.add(linesMesh);

    // ==========================================
    // Massive 3D Point Globe
    // ==========================================
    const globeGeometry = new THREE.SphereGeometry(150, 64, 64);
    const globeMaterial = new THREE.PointsMaterial({
        size: 3,
        color: 0x2563eb, // Electric Blue
        transparent: true,
        opacity: 0.6,
        blending: THREE.AdditiveBlending
    });
    const globe = new THREE.Points(globeGeometry, globeMaterial);
    
    // Position it deep so we fly towards it
    globe.position.set(0, 0, -500);
    scene.add(globe);

    // Network Group for holistic rotation (nodes + lines)
    const networkGroup = new THREE.Group();
    networkGroup.add(particlesMesh);
    networkGroup.add(linesMesh);
    scene.add(networkGroup);

    // ==========================================
    // Interaction Handlers
    // ==========================================
    let mouseX = 0;
    let mouseY = 0;
    let targetX = 0;
    let targetY = 0;
    const windowHalfX = window.innerWidth / 2;
    const windowHalfY = window.innerHeight / 2;

    document.addEventListener('mousemove', (event) => {
        mouseX = (event.clientX - windowHalfX);
        mouseY = (event.clientY - windowHalfY);
    });

    let scrollY = window.scrollY;
    let scrollPercent = 0;
    
    window.addEventListener('scroll', () => {
        scrollY = window.scrollY;
        // Calculate scroll percentage
        const maxScroll = document.body.scrollHeight - window.innerHeight;
        scrollPercent = maxScroll > 0 ? scrollY / maxScroll : 0;
    });

    window.addEventListener('resize', () => {
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
    });

    // ==========================================
    // Animation Loop
    // ==========================================
    const clock = new THREE.Clock();
    const connectDistance = 65; // Max distance to draw a line

    // Base color for lines (Electric Blue: 37, 99, 235 normalized)
    const baseColorR = 37 / 255;
    const baseColorG = 99 / 255;
    const baseColorB = 235 / 255;

    const tick = () => {
        const elapsedTime = clock.getElapsedTime();

        // 1. Update Particle Positions (Organic Drift)
        const positions = particlesGeometry.attributes.position.array;
        const origins = particlesGeometry.attributes.origin.array;
        const phases = particlesGeometry.attributes.phase.array;

        for (let i = 0; i < particlesCount; i++) {
            const i3 = i * 3;
            // X, Y, Z drifting on sine waves using their individual phases
            positions[i3] = origins[i3] + Math.sin(elapsedTime * 0.2 + phases[i3]) * 15;
            positions[i3 + 1] = origins[i3 + 1] + Math.cos(elapsedTime * 0.2 + phases[i3 + 1]) * 15;
            positions[i3 + 2] = origins[i3 + 2] + Math.sin(elapsedTime * 0.2 + phases[i3 + 2]) * 15;
        }
        particlesGeometry.attributes.position.needsUpdate = true;

        // 2. Calculate Connections (O(N^2) but optimized by low node count)
        let lineIdx = 0;
        let colorIdx = 0;
        let connectionCount = 0;

        for (let i = 0; i < particlesCount; i++) {
            const i3 = i * 3;
            const x1 = positions[i3];
            const y1 = positions[i3 + 1];
            const z1 = positions[i3 + 2];

            for (let j = i + 1; j < particlesCount; j++) {
                const j3 = j * 3;
                const x2 = positions[j3];
                const y2 = positions[j3 + 1];
                const z2 = positions[j3 + 2];

                const dx = x1 - x2;
                const dy = y1 - y2;
                const dz = z1 - z2;
                const distSq = dx * dx + dy * dy + dz * dz;

                if (distSq < connectDistance * connectDistance) {
                    linePositions[lineIdx++] = x1;
                    linePositions[lineIdx++] = y1;
                    linePositions[lineIdx++] = z1;
                    linePositions[lineIdx++] = x2;
                    linePositions[lineIdx++] = y2;
                    linePositions[lineIdx++] = z2;

                    const dist = Math.sqrt(distSq);
                    const alpha = 1.0 - (dist / connectDistance);
                    
                    const r = baseColorR * alpha;
                    const g = baseColorG * alpha;
                    const b = baseColorB * alpha;

                    lineColors[colorIdx++] = r;
                    lineColors[colorIdx++] = g;
                    lineColors[colorIdx++] = b;
                    lineColors[colorIdx++] = r;
                    lineColors[colorIdx++] = g;
                    lineColors[colorIdx++] = b;

                    connectionCount++;
                    if (connectionCount >= maxConnections) break;
                }
            }
            if (connectionCount >= maxConnections) break;
        }

        linesGeometry.setDrawRange(0, connectionCount * 2);
        linesGeometry.attributes.position.needsUpdate = true;
        linesGeometry.attributes.color.needsUpdate = true;

        // 3. Overall Rotation & Parallax
        targetX = mouseX * 0.0005;
        targetY = mouseY * 0.0005;

        networkGroup.rotation.y += 0.05 * (targetX - networkGroup.rotation.y);
        networkGroup.rotation.x += 0.05 * (targetY - networkGroup.rotation.x);
        networkGroup.rotation.z = elapsedTime * 0.02; // Slow base rotation

        // 4. Scrollytelling Fly-Through Effect
        // Base Z is 250, fly forward up to -350 as user scrolls (bringing us right up to the globe at -500)
        const startZ = 250;
        const endZ = -350;
        const targetCameraZ = startZ + (endZ - startZ) * scrollPercent;
        
        // Smoothly interpolate Z position
        camera.position.z += (targetCameraZ - camera.position.z) * 0.05;
        
        // Also add slight vertical pan
        camera.position.y = -scrollY * 0.05;
        camera.lookAt(0, 0, globe.position.z); 

        // 5. Globe Interactive Animation
        // Base slow rotation
        globe.rotation.y = elapsedTime * 0.1;
        globe.rotation.x = elapsedTime * 0.05;
        
        // Accelerate and scale based on scroll
        globe.rotation.y += scrollPercent * 4.0;
        const targetScale = 1.0 + (scrollPercent * 0.5);
        globe.scale.set(targetScale, targetScale, targetScale);

        // 5. Render
        renderer.render(scene, camera);

        window.requestAnimationFrame(tick);
    };

    tick();
});
