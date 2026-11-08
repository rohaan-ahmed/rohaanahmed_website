(() => {
    'use strict';
    const story = document.getElementById('career-story');
    const scroller = story.querySelector('.cv-scroll');
    const scenes = [...story.querySelectorAll('.cv-scene')];
    const links = [...story.querySelectorAll('.cv-years ol a')];
    const previous = story.querySelector('.cv-previous');
    const next = story.querySelector('.cv-next');
    const status = story.querySelector('.cv-scene-status');
    const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
    const mobile = matchMedia('(max-width: 620px)');
    const hint = story.querySelector('.cv-scroll-hint');
    const serviceScene = story.querySelector('#role-caf');
    const serviceChoices = [...serviceScene.querySelectorAll('[data-service]')];
    const servicePanels = [...serviceScene.querySelectorAll('[data-service-panel]')];
    const steps = scenes.flatMap((scene, sceneIndex) => scene === serviceScene
        ? serviceChoices.map(button => ({ sceneIndex, service: button.dataset.service }))
        : [{ sceneIndex }]);
    const sceneSteps = scenes.map((_, sceneIndex) => steps.flatMap((item, index) => item.sceneIndex === sceneIndex ? [index] : []));
    const serviceSteps = sceneSteps[scenes.indexOf(serviceScene)];
    const panelSteps = servicePanels.map(panel => steps.findIndex(item => item.service === panel.dataset.servicePanel));
    let horizontal = mobile.matches;
    let activeStep = -1;
    let selectedService = 'rcaf';
    let step = 320;
    let scrollFrame = 0;
    let measureFrame = 0;
    const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

    function paint() {
        scrollFrame = 0;
        if (horizontal !== mobile.matches) {
            requestMeasure();
            return;
        }
        const rawPosition = clamp((horizontal ? scroller.scrollLeft : scroller.scrollTop) / step, 0, steps.length - 1);
        const nearest = Math.round(rawPosition);
        const current = steps[nearest];
        if (current.service && current.service !== selectedService) {
            selectedService = current.service;
            renderService(selectedService);
        }
        const position = Math.abs(rawPosition - nearest) < .01 ? nearest : rawPosition;
        const servicePosition = clamp(position, serviceSteps[0], serviceSteps.at(-1));
        servicePanels.forEach((panel, index) => {
            const distance = servicePosition - panelSteps[index];
            panel.style.opacity = reducedMotion.matches
                ? Number(panel.dataset.servicePanel === selectedService)
                : Math.max(0, 1 - Math.abs(distance));
        });
        story.style.setProperty('--cv-progress', position / (steps.length - 1));
        scenes.forEach((scene, index) => {
            // Keep a shared scene visible between its consecutive scroll stops.
            const closest = clamp(position, sceneSteps[index][0], sceneSteps[index].at(-1));
            const distance = position - closest;
            const fade = clamp(Math.abs(distance) * 2, 0, 1);
            // Soften the brief dimming if native scrolling overshoots a service stop.
            const opacity = reducedMotion.matches
                ? Number(index === current.sceneIndex)
                : 1 - (scene === serviceScene ? fade ** 3 : fade);
            scene.style.opacity = opacity;
            scene.style.visibility = opacity > .001 ? 'visible' : 'hidden';
            scene.style.transform = reducedMotion.matches ? 'none' : `translate${horizontal ? 'X' : 'Y'}(${-distance * 18}px)`;
            scene.style.filter = reducedMotion.matches ? 'none' : `blur(${(1 - opacity) * 2}px)`;
        });
        if (nearest === activeStep) return;
        activeStep = nearest;
        scenes.forEach((scene, index) => {
            scene.classList.toggle('is-current', index === current.sceneIndex);
            scene.inert = index !== current.sceneIndex;
            scene.setAttribute('aria-hidden', String(index !== current.sceneIndex));
        });
        links.forEach((link, index) => {
            if (index === current.sceneIndex) link.setAttribute('aria-current', 'step');
            else link.removeAttribute('aria-current');
        });
        previous.disabled = activeStep === 0;
        next.disabled = activeStep === steps.length - 1;
        const counter = `${String(activeStep + 1).padStart(2, '0')} / ${String(steps.length).padStart(2, '0')}`;
        const label = current.service
            ? serviceChoices.find(button => button.dataset.service === current.service).querySelector('strong').textContent
            : scenes[current.sceneIndex].querySelector('.cv-organization').textContent;
        status.textContent = `${counter} · ${label}`;
        scenes[current.sceneIndex].querySelector('.cv-role-index').textContent = counter;
        if (horizontal) {
            const rail = story.querySelector('.cv-years ol');
            const selected = links[current.sceneIndex];
            rail.scrollTo({ left: selected.offsetLeft - rail.clientWidth / 2 + selected.offsetWidth / 2, behavior: reducedMotion.matches ? 'instant' : 'smooth' });
        }
    }
    function requestPaint() {
        if (!scrollFrame) scrollFrame = requestAnimationFrame(paint);
    }
    function measure() {
        measureFrame = 0;
        const previousStep = step;
        // Changing overflow axes resets the browser's old offset before resize runs.
        const axisChanged = horizontal !== mobile.matches;
        const position = axisChanged ? Math.max(activeStep, 0) : (horizontal ? scroller.scrollLeft : scroller.scrollTop) / step;
        horizontal = mobile.matches;
        if (axisChanged) activeStep = -1;
        const stacked = horizontal;
        const width = scroller.clientWidth;
        story.style.setProperty('--cv-panel-width', `${width}px`);
        const required = Math.max(...scenes.map(scene => {
            const style = getComputedStyle(scene);
            const roleHeight = scene.querySelector('.cv-role').getBoundingClientRect().height;
            const contextHeight = scene.querySelector('.cv-context').getBoundingClientRect().height;
            const contentHeight = stacked ? roleHeight + contextHeight + parseFloat(style.rowGap) : Math.max(roleHeight, contextHeight);
            return contentHeight + parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
        }));
        const height = Math.ceil(Math.max(stacked ? 440 : 490, required));
        step = horizontal ? width : Math.round(clamp(innerHeight * .4, 260, 380));
        story.style.setProperty('--cv-panel-height', `${height}px`);
        story.style.setProperty('--cv-step', `${step}px`);
        story.style.setProperty('--cv-track-height', `${height + step * (steps.length - 1)}px`);
        story.style.setProperty('--cv-track-width', `${width + step * (steps.length - 1)}px`);
        scroller.setAttribute('aria-label', `Experience timeline: ${horizontal ? 'swipe left or right' : 'scroll up or down'} to change roles`);
        hint.firstChild.textContent = horizontal ? 'Swipe to explore ' : 'Scroll to explore ';
        hint.querySelector('span').textContent = horizontal ? '↔' : '↕';
        if (axisChanged || step !== previousStep) {
            scroller.scrollTo({ left: horizontal ? position * step : 0, top: horizontal ? 0 : position * step, behavior: 'instant' });
        }
        paint();
    }
    function requestMeasure() {
        if (!measureFrame) measureFrame = requestAnimationFrame(measure);
    }
    function goTo(index, behavior = 'smooth') {
        const position = clamp(index, 0, steps.length - 1) * step;
        const motion = reducedMotion.matches ? 'instant' : behavior;
        scroller.scrollTo({ left: horizontal ? position : 0, top: horizontal ? 0 : position, behavior: motion });
        if (motion === 'instant') paint();
    }
    function renderService(service) {
        serviceChoices.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.service === service)));
        servicePanels.forEach(panel => {
            const inactive = panel.dataset.servicePanel !== service;
            panel.inert = inactive;
            panel.setAttribute('aria-hidden', String(inactive));
        });
    }
    renderService(selectedService);
    serviceChoices.forEach(button => button.addEventListener('click', () => {
        goTo(steps.findIndex(item => item.service === button.dataset.service));
        history.replaceState(null, '', `#role-${button.dataset.service}`);
    }));
    story.classList.add('is-enhanced');
    measure();
    scroller.addEventListener('scroll', requestPaint, { passive: true });
    // Keep input local to experience, and let native scrolling chain to the page at either end.
    story.addEventListener('wheel', event => {
        if (horizontal || event.ctrlKey || Math.abs(event.deltaX) > Math.abs(event.deltaY)) return;
        const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? scroller.clientHeight : 1);
        const destination = clamp(scroller.scrollTop + delta, 0, scroller.scrollHeight - scroller.clientHeight);
        if (Math.abs(destination - scroller.scrollTop) < .5) return;
        const bounds = scroller.getBoundingClientRect();
        const offset = document.querySelector('.content-navbar').getBoundingClientRect().bottom + 12;
        if (delta > 0 && bounds.top > offset + 2 && bounds.bottom > innerHeight - 10) {
            event.preventDefault();
            window.scrollBy({ top: Math.min(delta, bounds.top - offset), behavior: 'instant' });
            return;
        }
        if (bounds.top < offset - 2) {
            event.preventDefault();
            window.scrollBy({ top: bounds.top - offset, behavior: 'instant' });
            return;
        }
        if (scroller.contains(event.target)) return;
        event.preventDefault();
        scroller.scrollTop = destination;
    }, { passive: false });
    links.forEach((link, index) => link.addEventListener('click', event => {
        event.preventDefault();
        story.scrollIntoView({ block: 'start', behavior: 'instant' });
        goTo(sceneSteps[index][0]);
        history.replaceState(null, '', link.getAttribute('href'));
    }));
    previous.addEventListener('click', () => goTo(activeStep - 1));
    next.addEventListener('click', () => goTo(activeStep + 1));
    const resizeObserver = new ResizeObserver(requestMeasure);
    scenes.forEach(scene => {
        resizeObserver.observe(scene.querySelector('.cv-role'));
        resizeObserver.observe(scene.querySelector('.cv-context'));
    });
    window.addEventListener('resize', requestMeasure);
    window.addEventListener('load', requestMeasure);
    document.fonts?.ready.then(requestMeasure);
    reducedMotion.addEventListener('change', requestPaint);
    function openHash() {
        const service = location.hash === '#role-army' ? 'army' : location.hash === '#role-rcaf' ? 'rcaf' : null;
        const target = service ? '#role-caf' : location.hash;
        const index = service
            ? steps.findIndex(item => item.service === service)
            : steps.findIndex(item => `#${scenes[item.sceneIndex].id}` === target);
        if (index < 0) return;
        goTo(index, 'instant');
        story.scrollIntoView({ block: 'start', behavior: 'instant' });
    }
    requestAnimationFrame(openHash);
    window.addEventListener('hashchange', openHash);
    document.querySelectorAll('a[href="#experience"]').forEach(link => link.addEventListener('click', event => {
        event.preventDefault();
        history.replaceState(null, '', '#experience');
        story.scrollIntoView({ block: 'start', behavior: 'instant' });
    }));
})();
