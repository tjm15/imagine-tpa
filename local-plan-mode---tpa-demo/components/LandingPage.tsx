import React, { useState } from 'react';
import { Search, MapPin, ArrowRight, Loader2, Layout } from 'lucide-react';
import { searchLocation } from '../services/geocodingService';
import { LocationContext } from '../types';

interface LandingPageProps {
  onLocationSelect: (context: LocationContext) => void;
}

const LandingPage: React.FC<LandingPageProps> = ({ onLocationSelect }) => {
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState('');

  const executeSearch = async (searchQuery: string) => {
    if (!searchQuery.trim()) return;

    setSearching(true);
    setError('');

    const context = await searchLocation(searchQuery);
    
    if (context) {
      onLocationSelect(context);
    } else {
      setError('Location not found. Please try a different city or town.');
      setSearching(false);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    executeSearch(query);
  };

  const handleSuggestionClick = (city: string) => {
    setQuery(city);
    executeSearch(city);
  };

  const suggestedCities = [
    "Manchester",
    "Birmingham",
    "Bristol",
    "Leeds",
    "Newcastle",
    "Cambridge"
  ];

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans">
      <header className="px-6 py-4 flex items-center gap-2 border-b border-slate-100 bg-white">
        <div className="bg-indigo-600 p-1.5 rounded-lg text-white">
          <Layout size={20} />
        </div>
        <h1 className="font-bold text-lg tracking-tight text-slate-800">
          The Planner's Assistant
        </h1>
      </header>

      <main className="flex-1 flex flex-col items-center justify-center p-4">
        <div className="max-w-xl w-full text-center space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
          
          <div className="space-y-4">
            <h2 className="text-4xl font-extrabold text-slate-900 tracking-tight">
              Where are we planning today?
            </h2>
            <p className="text-lg text-slate-500">
              Enter a city, borough, or town in England to generate a bespoke Local Plan spatial strategy using AI.
            </p>
          </div>

          <form onSubmit={handleSearch} className="relative max-w-md mx-auto">
            <div className="relative group">
              <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                <MapPin className="h-5 w-5 text-slate-400 group-focus-within:text-indigo-500 transition-colors" />
              </div>
              <input
                type="text"
                className="block w-full pl-11 pr-12 py-4 bg-white border border-slate-200 rounded-xl text-lg text-slate-900 shadow-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
                placeholder="e.g. Camden, Shrewsbury"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                disabled={searching}
              />
              <button
                type="submit"
                disabled={searching || !query}
                className="absolute inset-y-2 right-2 px-4 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:bg-slate-300 disabled:cursor-not-allowed transition-colors flex items-center justify-center"
              >
                {searching ? <Loader2 className="animate-spin h-5 w-5" /> : <ArrowRight className="h-5 w-5" />}
              </button>
            </div>
            {error && <p className="mt-2 text-sm text-red-500 font-medium">{error}</p>}
          </form>

          <div className="pt-8">
            <p className="text-sm font-medium text-slate-400 uppercase tracking-wider mb-4">Popular Locations</p>
            <div className="flex flex-wrap justify-center gap-2">
              {suggestedCities.map(city => (
                <button
                  key={city}
                  type="button"
                  onClick={() => handleSuggestionClick(city)}
                  className="px-4 py-2 bg-white border border-slate-200 rounded-full text-sm text-slate-600 hover:border-indigo-300 hover:text-indigo-600 hover:bg-indigo-50 transition-all shadow-sm"
                >
                  {city}
                </button>
              ))}
            </div>
          </div>
        </div>
      </main>

      <footer className="py-6 text-center text-slate-400 text-sm">
        Powered by Google Gemini & OpenStreetMap
      </footer>
    </div>
  );
};

export default LandingPage;