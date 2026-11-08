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
    let active = -1;
    let step = 320;
    let scrollFrame = 0;
    let measureFrame = 0;
    const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

    function paint() {
        scrollFrame = 0;
        const rawPosition = clamp(scroller.scrollTop / step, 0, scenes.length - 1);
        const nearest = Math.round(rawPosition);
        const position = Math.abs(rawPosition - nearest) < .01 ? nearest : rawPosition;
        story.style.setProperty('--cv-progress', position / (scenes.length - 1));
        scenes.forEach((scene, index) => {
            const distance = position - index;
            const opacity = reducedMotion.matches ? Number(index === nearest) : Math.max(0, 1 - Math.abs(distance) * 2);
            scene.style.opacity = opacity;
            scene.style.visibility = opacity > .001 ? 'visible' : 'hidden';
            scene.style.transform = reducedMotion.matches ? 'none' : `translateY(${-distance * 18}px)`;
            scene.style.filter = reducedMotion.matches ? 'none' : `blur(${(1 - opacity) * 2}px)`;
        });
        if (nearest === active) return;
        active = nearest;
        scenes.forEach((scene, index) => {
            scene.classList.toggle('is-current', index === active);
            scene.inert = index !== active;
            scene.setAttribute('aria-hidden', String(index !== active));
        });
        links.forEach((link, index) => {
            if (index === active) link.setAttribute('aria-current', 'step');
            else link.removeAttribute('aria-current');
        });
        previous.disabled = active === 0;
        next.disabled = active === scenes.length - 1;
        status.textContent = `${String(active + 1).padStart(2, '0')} / ${String(scenes.length).padStart(2, '0')} · ${scenes[active].querySelector('.cv-organization').textContent}`;
        if (matchMedia('(max-width: 620px)').matches) {
            const rail = story.querySelector('.cv-years ol');
            const selected = links[active];
            rail.scrollTo({ left: selected.offsetLeft - rail.clientWidth / 2 + selected.offsetWidth / 2, behavior: reducedMotion.matches ? 'instant' : 'smooth' });
        }
    }
    function requestPaint() {
        if (!scrollFrame) scrollFrame = requestAnimationFrame(paint);
    }
    function measure() {
        measureFrame = 0;
        const position = scroller.scrollTop / step;
        const stacked = matchMedia('(max-width: 620px)').matches;
        const required = Math.max(...scenes.map(scene => {
            const style = getComputedStyle(scene);
            const roleHeight = scene.querySelector('.cv-role').getBoundingClientRect().height;
            const contextHeight = scene.querySelector('.cv-context').getBoundingClientRect().height;
            const contentHeight = stacked ? roleHeight + contextHeight + parseFloat(style.rowGap) : Math.max(roleHeight, contextHeight);
            return contentHeight + parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
        }));
        const height = Math.ceil(Math.max(stacked ? 440 : 490, required));
        step = Math.round(clamp(innerHeight * .4, 260, 380));
        story.style.setProperty('--cv-panel-height', `${height}px`);
        story.style.setProperty('--cv-step', `${step}px`);
        story.style.setProperty('--cv-track-height', `${height + step * (scenes.length - 1)}px`);
        scroller.scrollTop = position * step;
        paint();
    }
    function requestMeasure() {
        if (!measureFrame) measureFrame = requestAnimationFrame(measure);
    }
    function goTo(index, behavior = 'smooth') {
        scroller.scrollTo({ top: clamp(index, 0, scenes.length - 1) * step, behavior: reducedMotion.matches ? 'instant' : behavior });
    }
    story.classList.add('is-enhanced');
    measure();
    scroller.addEventListener('scroll', requestPaint, { passive: true });
    // Keep input local to experience, and let native scrolling chain to the page at either end.
    story.addEventListener('wheel', event => {
        if (event.ctrlKey || Math.abs(event.deltaX) > Math.abs(event.deltaY)) return;
        const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? scroller.clientHeight : 1);
        const destination = clamp(scroller.scrollTop + delta, 0, scroller.scrollHeight - scroller.clientHeight);
        if (Math.abs(destination - scroller.scrollTop) < .5) return;
        const bounds = scroller.getBoundingClientRect();
        const offset = document.querySelector('.cv-nav').getBoundingClientRect().bottom + 12;
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
        goTo(index);
        history.replaceState(null, '', link.getAttribute('href'));
    }));
    previous.addEventListener('click', () => goTo(active - 1));
    next.addEventListener('click', () => goTo(active + 1));
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
        const index = scenes.findIndex(scene => `#${scene.id}` === location.hash);
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
